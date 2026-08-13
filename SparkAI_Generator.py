"""Windows desktop entry point for the packaged Spark AI generator."""

from tools.sparkai_web import main


if __name__ == "__main__":
    raise SystemExit(main(["--open-browser"]))
