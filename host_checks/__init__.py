"""Real-host checks: explicit operator-run probes, never pytest-collected.

``python -m host_checks probe`` reports tool presence, the Bridge
version gate, and live modeling connectivity on THIS host. ``python -m
host_checks record-calibration`` turns operator-supplied canvas/PNG
dimensions into a recorded scale-fit verdict (Q1). Nothing here opens,
drives, or screenshots Desktop: calibration numbers come from an
operator-run capture, and this module only judges them.
"""
