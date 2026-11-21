# -*- coding: utf-8 -*-
VERSION = "0.4.0"


def classFactory(iface):
    from .plugin import SuitePlugin
    return SuitePlugin(iface)
