"""Docker HEALTHCHECK: query the gRPC health service and exit non-zero if not serving."""
import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app import config


def main() -> int:
    try:
        with grpc.insecure_channel(f"localhost:{config.PORT}") as channel:
            stub = health_pb2_grpc.HealthStub(channel)
            resp = stub.Check(health_pb2.HealthCheckRequest(service=""), timeout=3)
            return 0 if resp.status == health_pb2.HealthCheckResponse.SERVING else 1
    except grpc.RpcError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
