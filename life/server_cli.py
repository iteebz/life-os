from fncli import cli

from .server import serve


@cli("life")
def server(port: int = 5005):
    """Start the life dashboard web server."""
    print(f"life dashboard → http://0.0.0.0:{port}")
    serve(port=port)
