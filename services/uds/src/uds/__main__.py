"""Allow `python -m uds ...`."""
from uds.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
