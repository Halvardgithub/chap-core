"""Console script for climate_health."""
import dataclasses
import json
import webbrowser
from pathlib import PurePath, Path
from typing import Literal, Optional

import numpy as np
import pandas as pd
from cyclopts import App

from climate_health.external.external_model import get_model_maybe_yaml
from climate_health.spatio_temporal_data.multi_country_dataset import MultiCountryDataSet
from . import api
from climate_health.dhis2_interface.ChapProgram import ChapPullPost
from climate_health.dhis2_interface.json_parsing import add_population_data, predictions_to_datavalue
from climate_health.external.models.jax_models.model_spec import SSMForecasterNuts, NutsParams
from climate_health.external.models.jax_models.specs import SSMWithoutWeather, NaiveSSM
from climate_health.file_io import get_results_path
from climate_health.plotting.prediction_plot import plot_forecast_from_summaries
from climate_health.predictor import get_model, models, ModelType
from climate_health.file_io.example_data_set import datasets, DataSetType
from climate_health.time_period.date_util_wrapper import delta_month, Week
from .assessment.prediction_evaluator import evaluate_model
from .assessment.forecast import forecast as do_forecast, multi_forecast as do_multi_forecast
import logging
logging.basicConfig(level=logging.INFO)
app = App()


def append_to_csv(file_object, data_frame: pd.DataFrame):
    data_frame.to_csv(file_object, mode='a', header=False)



@app.command()
def evaluate(model_name: ModelType | str, dataset_name: DataSetType,  dataset_country: Optional[str] = None, prediction_length: int=6, n_splits: int =7, report_filename: Optional[str] = 'report.pdf'):
    '''
    Evaluate a model on a dataset using forecast cross validation
    '''
    logging.basicConfig(level=logging.INFO)
    dataset = datasets[dataset_name]
    dataset = dataset.load()

    if isinstance(dataset, MultiCountryDataSet):
        assert dataset_country is not None, 'Must specify a country for multi country datasets'
        assert dataset_country in dataset.countries, f'Country {dataset_country} not found in dataset. Countries: {dataset.countries}'
        dataset = dataset[dataset_country]

    model, model_name = get_model_maybe_yaml(model_name)
    model = model()
    results = evaluate_model(model, dataset, prediction_length=prediction_length, n_test_sets=n_splits, report_filename=report_filename)
    print(results)

@app.command()
def forecast(model_name: str, dataset_name: DataSetType, n_months: int,
            model_path: Optional[str] = None,
            out_path: Optional[str] = Path("./")):
    """
    Forecast n_months ahead using the given model and dataset

    Parameters:
        model_name: Name of the model to use, set to external to use an external model and specify the external model with model_path
        dataset_name: Name of the dataset to use, e.g. hydromet_5_filtered
        n_months: int: Number of months to forecast ahead
        model_path: Optional[str]: Path to the model if model_name is external. Can ge a github repo url starting with https://github.com and ending with .git or a path to a local directory.
        out_path: Optional[str]: Path to save the output file, default is the current directory
    """

    out_file = Path(out_path) / f'{model_name}_{dataset_name}_forecast_results_{n_months}.html'
    f = open(out_file, "w")
    figs = api.forecast(model_name, dataset_name, n_months, model_path)
    for fig in figs:
        f.write(fig.to_html())
    f.close()


@app.command()
def multi_forecast(model_name: str, dataset_name: DataSetType, n_months: int, pre_train_months: int, out_path: Path = Path('')):
    model, model_name = get_model_maybe_yaml(model_name)
    model = model()
    filename = out_path / f'{model_name}_{dataset_name}_multi_forecast_results_{n_months}.html'
    logging.info(f'Saving to {filename}')
    f = open(filename, "w")
    dataset = datasets[dataset_name].load()
    predictions_list = list(do_multi_forecast(model, dataset, n_months * delta_month, pre_train_delta=pre_train_months * delta_month))

    for location, true_data in dataset.items():
        local_predictions = [pred.get_location(location).data() for pred in predictions_list]
        fig = plot_forecast_from_summaries(local_predictions, true_data.data())
        f.write(fig.to_html())
    f.close()


@app.command()
def dhis_pull(base_url: str, username: str, password: str):
    path = Path('dhis2analyticsResponses/')
    path.mkdir(exist_ok=True, parents=True)
    from climate_health.dhis2_interface.ChapProgram import ChapPullPost
    process = ChapPullPost(dhis2Baseurl=base_url.rstrip('/'), dhis2Username=username, dhis2Password=password)
    full_data_frame = get_full_dataframe(process)
    disease_filename = (path / process.DHIS2HealthPullConfig.get_id()).with_suffix('.csv')
    full_data_frame.to_csv(disease_filename)


def get_full_dataframe(process):
    disease_data_frame = process.pullDHIS2Analytics()
    population_data_frame = process.pullPopulationData()
    full_data_frame = add_population_data(disease_data_frame, population_data_frame)
    return full_data_frame


@app.command()
def dhis_flow(base_url: str, username: str, password: str, n_periods=1):
    process = ChapPullPost(dhis2Baseurl=base_url.rstrip('/'), dhis2Username=username, dhis2Password=password)
    full_data_frame = get_full_dataframe(process)
    modelspec = SSMWithoutWeather()
    model = SSMForecasterNuts(modelspec, NutsParams(n_samples=10, n_warmup=10))
    model.train(full_data_frame)
    predictions = model.prediction_summary(Week(full_data_frame.end_timestamp))
    json_response = process.pushDataToDHIS2(predictions, modelspec.__class__.__name__, do_dict=False)
    # save json
    json_filename = Path('dhis2analyticsResponses/') / f'{modelspec.__class__.__name__}.json'
    with open(json_filename, 'w') as f:
        json.dump(json_response, f, indent=4)


@app.command()
def serve():
    '''
    Start CHAP as a backend server
    '''
    from .rest_api import main_backend
    main_backend()


@dataclasses.dataclass
class AreaPolygons:
    ...


'''@dataclasses.dataclass
class PredictionData:
    area_polygons: AreaPolygons
    health_data: SpatioTemporalDict[HealthData]
    climate_data: SpatioTemporalDict[ClimateData]
    population_data: SpatioTemporalDict[PopulationData]


def read_zip_folder(zip_file_path: str):
    #
    zip_file_reader = ZipFileReader(zip_file_path)
    ...


def convert_geo_json(geo_json_content) -> OurShapeFormat:
    ...

# def write_graph_data(geo_json_content) -> None:
#    ...





# GeoJson convertion
# zip folder reading
# GOthenburg
# Create prediction csv
'''


@app.command()
def dhis_zip_flow(zip_file_path: str, out_json: str, model_name: Optional[str] = None, docker_filename: Optional[str] = None):
    '''
    Run an forecasting evaluation on  data from a zip file from DHIS2, and save the results to a json file
    Run using the specified model_name, which can also be a path to a yaml file. Optionally specify a docker filename

    Parameters:
        zip_file_path: str: Path to the zip file
        out_json: str: Path to the output json file
        model_name: Optional[str]: Name of the model to use, or path to a yaml file
        docker_filename: Optional[str]: Path to a docker file
    '''

    api.dhis_zip_flow(zip_file_path, out_json, model_name, docker_filename=docker_filename)


def main_function():
    '''
    This function should just be type hinted with common types,
    and it will run as a command line function
    Simple function<

    >>> main()

    '''
    return


def main():
    app()


if __name__ == "__main__":
    app()
