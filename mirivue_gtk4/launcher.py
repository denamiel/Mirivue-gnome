"""Console entry point installed by the distribution's package manager."""

import runpy


def main():
    runpy.run_module('mirivue_gtk4', run_name='__main__', alter_sys=True)
