"""
RELIGHT STUDIO — RS-PRODUCT-1.0
================================
Main Application Entry Point (CLI)
Usage:
  python -m relight_studio [--port 8000] [--image path/to/image.jpg] [--cpu]
"""

import sys
import argparse
import uvicorn
from relight_studio.controller import StudioAppController
from relight_studio.server import create_app


def main():
    parser = argparse.ArgumentParser(description="Relight Studio — Virtual 3D Lighting Studio")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind application server (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--image", type=str, default=None, help="Initial photograph to load into studio")
    parser.add_argument("--cpu", action="store_true", help="Force CPU reference renderer instead of Metal GPU")
    args = parser.parse_args()

    print("=" * 80)
    print("💡 RELIGHT STUDIO — RS-PRODUCT-1.0")
    print("Artist-Controlled Virtual 3D Photography Studio")
    print(f"Platform: macOS / Apple Silicon | Compute: {'CPU Reference' if args.cpu else 'Native Metal GPU'}")
    print(f"Application Workspace URL: http://{args.host}:{args.port}")
    print("=" * 80)

    controller = StudioAppController(sample_image_path=args.image, use_metal=not args.cpu)
    app = create_app(controller)

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
