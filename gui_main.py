# gui_main.py
import os, sys

# ensure local imports work whether run as a script or as a module
sys.path.append(os.path.dirname(__file__))

from gui import run_gui  # now absolute within the project

if __name__ == "__main__":
    run_gui()
