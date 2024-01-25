import logging
from typing import Any, Dict

from opencensus.ext.azure.log_exporter import AzureLogHandler


def setup_azure_logging(logging_cfg: Dict[str, Any], pkg_name: str = None):
    """
    Sets up logging according to the configuration.

    Parameters
    ----------
    logging_cfg: logging configuration, for example:
        logging:
          loglevel_own: INFO  # override loglevel for packages defined in `own_packages`
          own_packages: ["__main__", "custom_package_1", "custom_package_2"]
          basic_config:
            # log config as arguments to `logging.basicConfig`
            level: INFO
            format: "%(asctime)s|||%(levelname)-8s|%(name)s|%(message)s"
            datefmt: "%Y-%m-%d %H:%M:%S"
          ai_instrumentation_key: "APPLICATION_INSIGHTS_CONNECTION_STRING"

    pkg_name: extra package to set up logging for

    Returns
    -------

    """
    logging.basicConfig(**logging_cfg["basic_config"])
    instrumentation_key = logging_cfg["ai_instrumentation_key"]
    azure_log_handler = AzureLogHandler(connection_string=instrumentation_key)
    azure_log_handler.setLevel(logging_cfg["loglevel_own"])

    packages = logging_cfg["own_packages"] + ([pkg_name] if pkg_name else [])

    for pkg in packages:
        pkg_logger = logging.getLogger(pkg)
        if pkg_logger.handlers:
            print(f"Handler for {pkg} has been set already.")
        else:
            pkg_logger.addHandler(azure_log_handler)
            print(f"pkg {pkg} has the following handlers: {pkg_logger.handlers}")
