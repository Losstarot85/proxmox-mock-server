import asyncio
import logging
import uvicorn
from server import create_app

# Disable uvicorn access logs to save I/O and CPU
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

async def main():
    milan_app = create_app("datacenter-milan")
    rome_app = create_app("datacenter-rome")
    naples_app = create_app("datacenter-naples")

    config_milan = uvicorn.Config(milan_app, host="0.0.0.0", port=8006, access_log=False)
    config_rome = uvicorn.Config(rome_app, host="0.0.0.0", port=8007, access_log=False)
    config_naples = uvicorn.Config(naples_app, host="0.0.0.0", port=8008, access_log=False)

    server_milan = uvicorn.Server(config_milan)
    server_rome = uvicorn.Server(config_rome)
    server_naples = uvicorn.Server(config_naples)

    # Run all servers concurrently within the same Python process
    await asyncio.gather(
        server_milan.serve(),
        server_rome.serve(),
        server_naples.serve(),
    )

if __name__ == "__main__":
    asyncio.run(main())
