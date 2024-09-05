from typing import Iterable, Tuple, Protocol, Optional, Type

from climate_health._legacy_dataset import IsSpatioTemporalDataSet
from climate_health.datatypes import ClimateHealthData, ClimateData, HealthData
from climate_health.spatio_temporal_data.temporal_dataclass import DataSet
from climate_health.time_period import Year, Month, TimePeriod
from climate_health.time_period.relationships import previous
import dataclasses


def split_period_on_resolution(param, param1, resolution) -> Iterable[Month]:
    pass


def extend_to(period, future_length):
    pass


class IsTimeDelta(Protocol):
    pass


def split_test_train_on_period(data_set: IsSpatioTemporalDataSet, split_points: Iterable[TimePeriod],
                               future_length: Optional[IsTimeDelta] = None, include_future_weather: bool = False,
                               future_weather_class: Type[ClimateData] = ClimateData):
    func = train_test_split_with_weather if include_future_weather else train_test_split

    if include_future_weather:
        return (train_test_split_with_weather(data_set, period, future_length, future_weather_class) for period in
                split_points)
    return (func(data_set, period, future_length) for period in split_points)


def split_train_test_with_future_weather(data_set: IsSpatioTemporalDataSet, split_points: Iterable[TimePeriod],
                                         future_length: Optional[IsTimeDelta] = None):
    return (train_test_split(data_set, period, future_length) for period in split_points)


# Should we index on split-timestamp, first time period, or complete time?
def train_test_split(data_set: IsSpatioTemporalDataSet, prediction_start_period: TimePeriod,
                     extension: Optional[IsTimeDelta] = None, restrict_test=True):
    last_train_period = previous(prediction_start_period)
    train_data = data_set.restrict_time_period(slice(None, last_train_period))
    if extension is not None:
        end_period = prediction_start_period.extend_to(extension)
    else:
        end_period = None
    if restrict_test:
        test_data = data_set.restrict_time_period(slice(prediction_start_period, end_period))
    else:
        test_data = data_set
    return train_data, test_data


def train_test_generator(dataset: DataSet, prediction_length: int, n_test_sets: int = 1) -> tuple[
    DataSet, Iterable[tuple[DataSet, DataSet]]]:
    '''
    Genereate a train set along with an iterator of test data that contains tuples of full data up until a
    split point and data without target variables for the remaining steps
    '''
    split_idx = -(prediction_length + n_test_sets)
    train_set = dataset.restrict_time_period(slice(None, dataset.period_range[split_idx]))
    historic_data = (dataset.restrict_time_period(slice(None, dataset.period_range[split_idx + i]))
                     for i in range(n_test_sets))
    future_data = [dataset.restrict_time_period(slice(dataset.period_range[split_idx + i + 1],
                                                      dataset.period_range[split_idx + i + prediction_length]))
                   for i in range(n_test_sets)]
    masked_future_data = (dataset.remove_field('disease_cases') for dataset in future_data)
    return train_set, zip(historic_data, masked_future_data, future_data)


def train_test_split_with_weather(data_set: DataSet, prediction_start_period: TimePeriod,
                                  extension: Optional[IsTimeDelta] = None,
                                  future_weather_class: Type[ClimateData] = ClimateData):
    train_set, test_set = train_test_split(data_set, prediction_start_period, extension)
    tmp_values: Iterable[Tuple[str, ClimateHealthData]] = ((loc, temporal_data.data()) for loc, temporal_data in
                                                           test_set.items())
    future_weather = test_set.remove_field('disease_cases')  # SpatioTemporalDict(
    train_periods = {str(period) for data in train_set.data() for period in data.data().time_period}
    future_periods = {str(period) for data in future_weather.data() for period in data.data().time_period}
    assert train_periods & future_periods == set(), f"Train and future weather data overlap: {train_periods & future_periods}"
    return train_set, test_set, future_weather


def get_split_points_for_data_set(data_set: IsSpatioTemporalDataSet, max_splits: int, start_offset=1) -> list[
    TimePeriod]:
    periods = next(iter(
        data_set.data())).data().time_period  # Uses the time for the first location, assumes it to be the same for all!
    return get_split_points_for_period_range(max_splits, periods, start_offset)


def get_split_points_for_period_range(max_splits, periods, start_offset):
    delta = (len(periods) - 1 - start_offset) // (max_splits + 1)
    return list(periods)[start_offset + delta::delta][:max_splits]
