"""hermes engine gRPC daemon.

Registers on one lattice port (:50651):
  hermes.engine.HermesEngine     (native surface)
  zndx.engine.v1.Engine          (capability convenience face)
  inference.GRPCInferenceService (mandatory OIP)

Lattice accept is Engine/Status with project=hermes, capability=agent.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import grpc
from grpc_reflection.v1alpha import reflection

import hsengine
from hsengine.config import get_int, get_str
from hsengine.engine import complete as complete_svc
from hsengine.engine import federation, lineage, oip_servicer, probe, s2s, surfaces
from hsengine.engine.generated import hermes_engine_pb2 as pb
from hsengine.engine.generated import hermes_engine_pb2_grpc as pb_grpc
from hsengine.engine.generated.inference.v2 import open_inference_grpc_pb2 as oip_pb
from hsengine.engine.generated.inference.v2 import open_inference_grpc_pb2_grpc as oip_grpc
from hsengine.engine.generated.zndx.engine.v1 import engine_pb2 as zpb
from hsengine.engine.generated.zndx.engine.v1 import engine_pb2_grpc as zpb_grpc
from hsengine.engine.oip_tensors import STATUS_CONSULTING
from hsengine.engine.workloads import WorkloadTable

log = logging.getLogger("hsengine.engine")

CAPABILITY_AGENT = "agent"
CAPABILITY_INSTRUCT = "instruct"
PROJECT = "hermes"

_WORKLOADS = WorkloadTable()


def _route_detail(route: federation.Route | None) -> dict | None:
    if route is None:
        return None
    return {
        "peer": route.peer,
        "project": route.project,
        "capability": route.capability,
        "model": route.model,
        "healthy": route.healthy,
    }


def _inference_detail() -> str:
    fed_ready, fed_detail = federation.inference_ready(CAPABILITY_AGENT)
    route = federation.preferred_route(CAPABILITY_AGENT)
    return json.dumps(
        {
            "mode": "federated+oip",
            "oip": True,
            "stream": True,
            "status_note": STATUS_CONSULTING,
            "federation": {
                "ready": fed_ready,
                "detail": fed_detail,
                "peers": federation.federation_peers(),
                "accepted": federation.accepted_capabilities(CAPABILITY_AGENT),
                "route": _route_detail(route),
            },
            "grpc": {
                "host": get_str("hermes.engine.grpc.host"),
                "port": get_int("hermes.engine.grpc.port"),
                "services": [
                    "zndx.engine.v1.Engine",
                    "hermes.engine.HermesEngine",
                    "inference.GRPCInferenceService",
                ],
            },
        },
        sort_keys=True,
    )


def _status_endpoints(dash: probe.SurfaceProbe) -> list:
    inf_detail = _inference_detail()
    fed_ready, _ = federation.inference_ready(CAPABILITY_AGENT)
    route = federation.preferred_route(CAPABILITY_AGENT)
    endpoints = [
        zpb.Endpoint(
            capability=CAPABILITY_AGENT,
            model="hsengine",
            healthy=True,
            gpu_ids=[],
            detail=json.dumps(
                {
                    "dashboard": {"url": dash.url, "healthy": dash.healthy, "probe": dash.detail},
                    "primary_ui": surfaces.primary_ui_url(),
                    "inference": json.loads(inf_detail),
                },
                sort_keys=True,
            ),
        )
    ]
    if federation.federation_peers():
        endpoints.append(
            zpb.Endpoint(
                capability=CAPABILITY_INSTRUCT,
                model=(route.model if route and route.model else "federated"),
                healthy=fed_ready,
                gpu_ids=[],
                detail=inf_detail,
            )
        )
    return endpoints


class HermesEngineServicer(pb_grpc.HermesEngineServicer):
    async def EngineStatus(self, request, context):
        capabilities = [CAPABILITY_AGENT]
        if federation.federation_peers():
            capabilities.append(CAPABILITY_INSTRUCT)
        return pb.EngineStatusReply(
            project=PROJECT,
            version=hsengine.__version__,
            capabilities=capabilities,
        )

    async def GetAgentInstance(self, request, context):
        dash = await asyncio.to_thread(probe.probe_dashboard)
        gw = await asyncio.to_thread(probe.probe_gateway)
        return pb.GetAgentInstanceReply(
            healthy=dash.healthy,
            dashboard_url=dash.url,
            gateway_url=gw.url,
            detail=f"dashboard={dash.detail}; gateway={gw.detail}",
        )


class ZndxEngineServicer(zpb_grpc.EngineServicer):
    """Shared federation face: Status, ServerQuery, federated Complete, Yield, lineage."""

    async def Status(self, request, context):
        dash = await asyncio.to_thread(probe.probe_dashboard)
        gw = await asyncio.to_thread(probe.probe_gateway)
        endpoints = await asyncio.to_thread(_status_endpoints, dash)
        return zpb.StatusResponse(
            project=PROJECT,
            endpoints=endpoints,
            total_gpus=0,
            surfaces=surfaces.local_surfaces(dash.healthy, gateway_healthy=gw.healthy),
        )

    async def ServerQuery(self, request, context):
        dash = await asyncio.to_thread(probe.probe_dashboard)
        return await asyncio.to_thread(
            s2s.local_response, int(request.kind or 0), dashboard_healthy=dash.healthy
        )

    async def Complete(self, request, context):
        try:
            result = await asyncio.to_thread(
                complete_svc.complete,
                capability=request.capability or CAPABILITY_AGENT,
                prompt=request.prompt or "",
                system_prompt=request.system_prompt or "",
                max_tokens=request.max_tokens or 4096,
                temperature=request.temperature if request.temperature else 0.7,
                json_schema=request.json_schema or "",
            )
        except RuntimeError as e:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details(str(e))
            return zpb.CompleteResponse()
        except Exception as e:
            log.exception("Complete failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"complete failed: {e}")
            return zpb.CompleteResponse()
        return zpb.CompleteResponse(
            text=result.text,
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            latency_ms=result.latency_ms,
            reasoning_content=result.reasoning_content,
            finish_reason=result.finish_reason or "stop",
        )

    async def Yield(self, request, context):
        ended, msg = _WORKLOADS.yield_one(request.workload_id)
        return zpb.YieldResponse(
            ok=True,
            process_ended=ended,
            restore_started=False,
            message=msg,
        )

    async def RecordLineage(self, request, context):
        return await asyncio.to_thread(lineage.record, request.event_json, request.event_type)

    async def Remediate(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details(
            "Remediate is served by Aegir (instruct / ontology). "
            "Hermes engine capability is agent."
        )
        return zpb.RemediationResponse()

    async def WatchWorkload(self, request, context):
        generation = 0
        while not context.cancelled():
            yield zpb.WorkloadProfile(
                phase=zpb.WORKLOAD_PHASE_SETTLED,
                generation=generation,
                intents=[],
                settled_at_unix_ms=int(time.time() * 1000),
                detail="hsengine: no GPU serving set (empty intents is honest)",
            )
            try:
                await asyncio.sleep(15)
            except asyncio.CancelledError:
                return
            generation += 1


async def serve() -> None:
    host = get_str("hermes.engine.grpc.host")
    port = get_int("hermes.engine.grpc.port")
    s2s.stamp_running_sha()

    server = grpc.aio.server()
    pb_grpc.add_HermesEngineServicer_to_server(HermesEngineServicer(), server)
    zpb_grpc.add_EngineServicer_to_server(ZndxEngineServicer(), server)
    oip_grpc.add_GRPCInferenceServiceServicer_to_server(
        oip_servicer.OipInferenceServicer(), server
    )
    service_names = (
        pb.DESCRIPTOR.services_by_name["HermesEngine"].full_name,
        zpb.DESCRIPTOR.services_by_name["Engine"].full_name,
        oip_pb.DESCRIPTOR.services_by_name["GRPCInferenceService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    bound = server.add_insecure_port(f"{host}:{port}")
    if bound == 0:
        raise SystemExit(f"DENY: could not bind {host}:{port} — is another engine on it?")
    await server.start()
    log.info(
        "hermes engine serving on %s:%s "
        "(native + zndx.engine.v1 + OIP + reflection; "
        "capability=agent; surfaces=%s; peers=%s)",
        host,
        port,
        [s.url for s in surfaces.local_surfaces(True) if s.kind == surfaces.SURFACE_PRIMARY],
        federation.federation_peers(),
    )
    await server.wait_for_termination()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    asyncio.run(serve())
