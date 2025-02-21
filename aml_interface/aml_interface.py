import logging
import os
import shutil

from azure.ai.ml import MLClient
from azure.ai.ml.entities import BuildContext, Environment, ManagedIdentityConfiguration
from azure.identity import DefaultAzureCredential, InteractiveBrowserCredential

logger = logging.getLogger(__name__)


def delete_file(file_path):
    try:
        os.remove(file_path)
        logger.info(f"{file_path} has been deleted.")
    except FileNotFoundError:
        logger.error(f"{file_path} does not exist.")
    except Exception as e:
        logger.error(f"Failed to remove file '{file_path}': {str(e)}")
        raise Exception(f"Failed to remove file '{file_path}': {e}")


class AMLInterface:
    """This class provides an interface to interact with Azure ML.

    Attributes
    ----------
    ml_client :
        Instance of :class:`azureml.core.Workspace`
    """

    def __init__(self):
        """Initiate AMLInterface based on the Azure config.json file."""
        self.ml_client = MLClient.from_config(self._connect())
        logger.info(
            f"Retrieved the following workspace: {self.ml_client.workspace_name}"
        )

        # Initialize Azure ML workspace details
        self.workspace_name = self.ml_client.workspace_name
        self.subscription_id = self.ml_client.subscription_id
        self.resource_group = self.ml_client.resource_group_name

        self.azureml_path = "azureml://subscriptions/{subscription}/resourcegroups/{resourcegroup}/workspaces/{workspace}/datastores/{datastore_name}/paths/"

    @staticmethod
    def _connect():
        """
        Connects to the ML workspace and other components using the Managed Identity of the workspace
        """
        try:
            credential = DefaultAzureCredential()
            # Check if given credential can get token successfully.
            credential.get_token("https://management.azure.com/.default")
        except Exception:
            # Fall back to InteractiveBrowserCredential in case DefaultAzureCredential not work
            # This will open a browser page for
            logger.info("Using InteractiveBrowserCredential login...")
            credential = InteractiveBrowserCredential()
        return credential

    def get_datastore_full_path(self, datastore_name):
        full_path = self.azureml_path.format(
            subscription=self.subscription_id,
            resourcegroup=self.resource_group,
            workspace=self.ml_client.workspace_name,
            datastore_name=datastore_name,
        )

        return full_path

    def create_aml_environment(
        self,
        env_name: str,
        build_context_path: str,
        dockerfile_path: str,
        build_cluster: str = "defaultBuildClusterCvt",
        build_context_files: list[str] = ["poetry.lock", "pyproject.toml"],
    ) -> Environment:
        """Creates an AML environment based on the provided dockerfile image.
        Installs the pip packages present in the env where the code is run.

        Parameters
        ----------
        env_name : str
            Name to give to the new environment.
        build_context_path: str
            Path that contains the build context.
        dockerfile_path: str
            Dockerfile path inside the build context.
        build_cluster: str
            Cluster to be used when building environments within Analyse Services.
        build_context_files: list[str] = ["poetry.lock", "pyproject.toml"]
            Local files to be added to the build context

        Returns
        -------
        : Environment
            Created environment.
        """
        ws = self.ml_client.workspaces.get(name=self.ml_client.workspace_name)
        ws.image_build_compute = build_cluster

        for file in build_context_files:
            shutil.copyfile(file, f"{build_context_path}/{file}")

        env = Environment(
            name=env_name,
            build=BuildContext(
                path=build_context_path,
                dockerfile_path=dockerfile_path,
            ),
        )
        self.ml_client.environments.create_or_update(env)

        for file in build_context_files:
            delete_file(f"{build_context_path}/{file}")

        return env

    def submit_command_job(self, job):
        """
        Examples
        ________
        aml_interface = AMLInterface()
        env = aml_interface.create_aml_environment(experiment_details["env_name"])

        input_data_path = ""
        output_data_path = ""
        inputs = {
            "input_data": Input(type=AssetTypes.URI_FILE, path=input_data_path)
        }
        outputs = {
            "output_folder": Output(type=AssetTypes.URI_FOLDER, path=output_data_path)
        }

        job = command(
            code=".",  # local path where the code is stored
            command="PYTHONPATH=. python file_to_execute.py --input_data ${{inputs.input_data}} --output_folder ${{outputs.output_folder}}",
            inputs=inputs,
            outputs=outputs,
            environment=env,
            compute=experiment_details["compute_name"],
        )
        submitted_job = aml_interface.submit_command_job(job)

        Parameters
        ----------
        job
            The job to be created or updated.

        Returns
        -------
            The created or updated resource.

        """
        return self.ml_client.create_or_update(job)

    def submit_pipeline_job(self, pipeline_job, experiment_name):
        """

        Examples
        --------
        aml_interface = AMLInterface()
        aml_interface.create_aml_environment(
            experiment_details["env_name"]
        )

        input_data_path = ""
        output_data_path = ""
        input_data = Input(type=AssetTypes.URI_FILE, path=input_data_path)

        metadata_pipeline_job = metadata_pipeline(
            input_data=input_data,
            output_data_path=output_data_path
        )
        metadata_pipeline_job.settings.default_compute = experiment_details["compute_name"]

        pipeline_job = aml_interface.submit_pipeline_job(pipeline_job=metadata_pipeline_job,
                                                         experiment_name="metadata_pipeline")
        aml_interface.wait_until_job_completes(pipeline_job.name)

        Parameters
        ----------
        pipeline_job
        experiment_name

        Returns
        -------

        """
        return self.ml_client.jobs.create_or_update(
            pipeline_job, experiment_name=experiment_name
        )

    def submit_pipeline_experiment(
        self, pipeline_function, experiment_name, default_compute
    ):
        """
        Submits a pipeline experiment to AzureML.

        Parameters
        ----------
        pipeline_function:
            Function of the pipeline. Decorated with @pipeline.
        experiment_name:
            Name to give to the experiment.
        default_compute:
            Compute name to use to run the pipeline.

        """
        pipeline_job = pipeline_function()
        pipeline_job.identity = ManagedIdentityConfiguration()
        pipeline_job.settings.default_compute = default_compute

        pipeline_job = self.submit_pipeline_job(
            pipeline_job=pipeline_job, experiment_name=experiment_name
        )
        self.wait_until_job_completes(pipeline_job.name)

    def wait_until_job_completes(self, job_name):
        self.ml_client.jobs.stream(job_name)
