import logging
import sys

__author__ = 'gkralik'


def configure_logging(level=logging.INFO):
    logging.basicConfig(stream=sys.stdout, level=level)


if sys.version_info < (3, 2):
    import optparse

    def parse_arguments():
        #return parser.parse_args()
        parser = optparse.OptionParser()
        #parser.add_option('-v', '--version', action="version", version="0.1", help="print version info and exit.")
        parser.add_option('-i', type=str, metavar="hostname:port", dest="ide",
                          help="listener port for IDE processes (defaults to 127.0.0.1:9001", default="127.0.0.1:9001")
        parser.add_option('-d', type=str, metavar="hostname:port", dest="dbg",
                          help="listener port for debug processes (defaults to 127.0.0.1:9000",
                          default="127.0.0.1:9000")
        parser.add_option('-l', type=str, metavar="LOGLEVEL", dest="loglevel",
                          help="Log verbosity. Accepted values are CRITICAL, ERROR, WARN, INFO (default), DEBUG",
                          default="INFO")

        return parser.parse_args()[0]
else:
    import argparse

    def parse_arguments():
        parser = argparse.ArgumentParser()
        parser.add_argument('-v', '--version', action="version", version="0.1", help="print version info and exit.")
        parser.add_argument('-i', type=str, metavar="hostname:port", dest="ide",
                            help="listener port for IDE processes (defaults to 127.0.0.1:9001",
                            default="127.0.0.1:9001")
        parser.add_argument('-d', type=str, metavar="hostname:port", dest="dbg",
                            help="listener port for debug processes (defaults to 127.0.0.1:9000",
                            default="127.0.0.1:9000")
        parser.add_argument('-l', type=str, metavar="LOGLEVEL", dest="loglevel",
                            help="Log verbosity. Accepted values are CRITICAL, ERROR, WARN, INFO (default), DEBUG",
                            default="INFO")
        return parser.parse_args()