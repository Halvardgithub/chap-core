from typing import Generic, Iterable, Tuple, Type, Callable

import numpy as np
import pandas as pd

from ..api_types import PeriodObservation
from .._legacy_dataset import TemporalIndexType, FeaturesT
from ..datatypes import Location, add_field, remove_field, TimeSeriesArray, TimeSeriesData
from ..time_period import PeriodRange
from ..time_period.date_util_wrapper import TimeStamp
import dataclasses


class TemporalDataclass(Generic[FeaturesT]):
    '''
    Wraps a dataclass in a object that is can be sliced by time period.
    Call .data() to get the data back.
    '''

    def __init__(self, data: FeaturesT):
        self._data = data

    def __repr__(self):
        return f'{self.__class__.__name__}({self._data})'

    def _restrict_by_slice(self, period_range: slice):
        assert period_range.step is None
        start, stop = (None, None)
        if period_range.start is not None:
            start = self._data.time_period.searchsorted(period_range.start)
        if period_range.stop is not None:
            stop = self._data.time_period.searchsorted(period_range.stop, side='right')
        return self._data[start:stop]

    def fill_to_endpoint(self, end_time_stamp: TimeStamp) -> 'TemporalDataclass[FeaturesT]':
        if self.end_timestamp == end_time_stamp:
            return self
        n_missing = self._data.time_period.delta.n_periods(self.end_timestamp, end_time_stamp)
        #n_missing = (end_time_stamp - self.end_timestamp) // self._data.time_period.delta
        assert n_missing >= 0, (f'{n_missing} < 0', end_time_stamp, self.end_timestamp)
        old_time_period = self._data.time_period
        new_time_period = PeriodRange(old_time_period.start_timestamp, end_time_stamp, old_time_period.delta)
        d = {field.name: getattr(self._data, field.name) for field in dataclasses.fields(self._data) if
             field.name != 'time_period'}

        for name, data in d.items():
            d[name] = np.pad(data.astype(float), (0, n_missing),
                             constant_values=np.nan)
        return TemporalDataclass(
            self._data.__class__(new_time_period, **d))

    def fill_to_range(self, start_timestamp, end_timestamp):
        if self.end_timestamp == end_timestamp and self.start_timestamp==start_timestamp:
            return self
        n_missing_start = self._data.time_period.delta.n_periods(start_timestamp, self.start_timestamp)
        #n_missing_start = (self.start_timestamp - start_timestamp) // self._data.time_period.delta
        n_missing = (end_timestamp - self.end_timestamp) // self._data.time_period.delta
        assert n_missing >= 0, (f'{n_missing} < 0', end_timestamp, self.end_timestamp)
        assert n_missing_start >= 0, (f'{n_missing} < 0', end_timestamp, self.end_timestamp)
        old_time_period = self._data.time_period
        new_time_period = PeriodRange(start_timestamp, end_timestamp, old_time_period.delta)
        d = {field.name: getattr(self._data, field.name) for field in dataclasses.fields(self._data) if
             field.name != 'time_period'}

        for name, data in d.items():
            d[name] = np.pad(data.astype(float), (n_missing_start, n_missing),
                             constant_values=np.nan)
        return TemporalDataclass(
            self._data.__class__(new_time_period, **d))

    def restrict_time_period(self, period_range: TemporalIndexType) -> 'TemporalDataclass[FeaturesT]':
        assert isinstance(period_range, slice)
        assert period_range.step is None
        if hasattr(self._data.time_period, 'searchsorted'):
            return TemporalDataclass(self._restrict_by_slice(period_range))
        mask = np.full(len(self._data.time_period), True)
        if period_range.start is not None:
            mask = mask & (self._data.time_period >= period_range.start)
        if period_range.stop is not None:
            mask = mask & (self._data.time_period <= period_range.stop)
        return TemporalDataclass(self._data[mask])

    def data(self) -> Iterable[FeaturesT]:
        return self._data

    def to_pandas(self) -> pd.DataFrame:
        return self._data.to_pandas()

    def join(self, other):
        return TemporalDataclass(np.concatenate([self._data, other._data]))

    @property
    def start_timestamp(self) -> pd.Timestamp:
        return self._data.time_period[0].start_timestamp

    @property
    def end_timestamp(self) -> pd.Timestamp:
        return self._data.time_period[-1].end_timestamp


class DataSet(Generic[FeaturesT]):
    '''
    Class representing severeal time series at different locations.
    '''

    def __init__(self, data_dict: dict[str, FeaturesT]):
        self._data_dict = {loc: TemporalDataclass(data) if not isinstance(data, TemporalDataclass) else data for
                           loc, data in data_dict.items()}

    def __repr__(self):
        return f'{self.__class__.__name__}({self._data_dict})'

    def __getitem__(self, location: Location) -> TemporalDataclass[FeaturesT]:
        return self._data_dict[location].data()

    def keys(self):
        return self._data_dict.keys()

    def items(self):
        return ((k, d.data()) for k, d in self._data_dict.items())

    def values(self):
        return (d.data() for d in self._data_dict.values())

    @property
    def period_range(self) -> PeriodRange:
        first_period_range = self._data_dict[next(iter(self._data_dict))].data().time_period
        assert first_period_range.start_timestamp == first_period_range.start_timestamp
        assert first_period_range.end_timestamp == first_period_range.end_timestamp
        return first_period_range

    @property
    def start_timestamp(self) -> pd.Timestamp:
        return min(data.start_timestamp for data in self.data())

    @property
    def end_timestamp(self) -> pd.Timestamp:
        return max(data.end_timestamp for data in self.data())

    def get_locations(self, location: Iterable[Location]) -> 'DataSet[FeaturesT]':
        return self.__class__({loc: self._data_dict[loc] for loc in location})

    def get_location(self, location: Location) -> FeaturesT:
        return self._data_dict[location]

    def restrict_time_period(self, period_range: TemporalIndexType) -> 'DataSet[FeaturesT]':
        return self.__class__(
            {loc: data.restrict_time_period(period_range) for loc, data in self._data_dict.items()})

    def locations(self) -> Iterable[Location]:
        return self._data_dict.keys()

    def data(self) -> Iterable[FeaturesT]:
        return self._data_dict.values()

    #def items(self) -> Iterable[Tuple[Location, FeaturesT]]:
    #    return self._data_dict.items()

    def _add_location_to_dataframe(self, df, location):
        df['location'] = location
        return df

    def to_pandas(self) -> pd.DataFrame:
        ''' Join the pandas frame for all locations with locations as column'''
        tables = [self._add_location_to_dataframe(data.to_pandas(), location) for location, data in
                  self._data_dict.items()]
        return pd.concat(tables)

    def interpolate(self):
        return self.__class__(
            {loc: TemporalDataclass(data.data().interpolate()) for loc, data in self.items()})

    @classmethod
    def _fill_missing(cls, data_dict: dict[str, TemporalDataclass[FeaturesT]]):
        ''' Fill missing values in a dictionary of TemporalDataclasses'''
        end = max(data.end_timestamp for data in data_dict.values())
        start = min(data.start_timestamp for data in data_dict.values())
        for location, data in data_dict.items():
            data_dict[location] = data.fill_to_range(start, end)
        return data_dict

    @classmethod
    def from_pandas(cls, df: pd.DataFrame, dataclass: Type[FeaturesT], fill_missing=False) -> 'DataSet[FeaturesT]':
        '''
        Create a SpatioTemporalDict from a pandas dataframe.
        The dataframe needs to have a 'location' column, and a 'time_period' column.
        The time_period columnt needs to have strings that can be parsed into a period.
        All fields in the dataclass needs to be present in the dataframe.
        If 'fill_missing' is True, missing values will be filled with np.nan. Else all the time series needs to be
        consecutive.


        Parameters
        ----------
        df : pd.DataFrame
            The dataframe
        dataclass : Type[FeaturesT]
            The dataclass to use for the time series
        fill_missing : bool, optional
            If missing values should be filled, by default False

        Returns
        -------
        DataSet[FeaturesT]
            The SpatioTemporalDict

        Examples
        --------
        >>> import pandas as pd
        >>> from climate_health.spatio_temporal_data.temporal_dataclass import DataSet
        >>> from climate_health.datatypes import HealthData
        >>> df = pd.DataFrame({'location': ['Oslo', 'Oslo', 'Bergen', 'Bergen'],
        ...                    'time_period': ['2020-01', '2020-02', '2020-01', '2020-02'],
        ...                    'disease_cases': [10, 20, 30, 40]})
        >>> DataSet.from_pandas(df, HealthData)
        '''
        data_dict = {}
        for location, data in df.groupby('location'):
            data_dict[location] = TemporalDataclass(dataclass.from_pandas(data, fill_missing))
        data_dict = cls._fill_missing(data_dict)

        return cls(data_dict)

    def to_csv(self, file_name: str, mode='w'):
        self.to_pandas().to_csv(file_name, mode=mode)

    @classmethod
    def df_from_pydantic_observations(cls, observations: list[PeriodObservation])-> TimeSeriesData:
        df = pd.DataFrame([obs.model_dump() for obs in observations])
        dataclass = TimeSeriesData.create_class_from_basemodel(type(observations[0]))
        return dataclass.from_pandas(df)

    @classmethod
    def from_period_observations(cls, observation_dict: dict[str, list[PeriodObservation]]) -> 'DataSet[TimeSeriesData]':
        '''
        Create a SpatioTemporalDict from a dictionary of PeriodObservations.
        The keys are the location names, and the values are lists of PeriodObservations.

        Parameters
        ----------
        observation_dict : dict[str, list[PeriodObservation]]
            The dictionary of observations

        Returns
        -------
        DataSet[TimeSeriesData]
            The SpatioTemporalDict

        Examples
        --------
        >>> from climate_health.spatio_temporal_data.temporal_dataclass import DataSet
        >>> from climate_health.api_types import PeriodObservation
        >>> class HealthObservation(PeriodObservation):
        ...     disease_cases: int
        >>> observations = {'Oslo': [HealthObservation(time_period='2020-01', disease_cases=10),
        ...                          HealthObservation(time_period='2020-02', disease_cases=20)]}
        >>> DataSet.from_period_observations(observations)
        >>> DataSet.to_pandas()
        '''
        data_dict = {}
        for location, observations in observation_dict.items():
            data_dict[location] = TemporalDataclass(cls.df_from_pydantic_observations(observations))
        return cls(data_dict)

    @classmethod
    def from_csv(cls, file_name: str, dataclass: Type[FeaturesT]) -> 'DataSet[FeaturesT]':
        return cls.from_pandas(pd.read_csv(file_name), dataclass)

    def join_on_time(self, other: 'DataSet[FeaturesT]') -> 'DataSet[Tuple[FeaturesT, FeaturesT]]':
        ''' Join two SpatioTemporalDicts on time. Returns a new SpatioTemporalDict.
        Assumes other is later in time.
        '''
        return self.__class__({loc: self._data_dict[loc].join(other._data_dict[loc]) for loc in self.locations()})

    def add_fields(self, new_type, **kwargs: dict[str, Callable]):
        return self.__class__({loc: add_field(data.data(), new_type, **{key: func(data.data()) for key, func in kwargs.items()}) for loc, data in self.items()})

    def remove_field(self, field_name, new_class=None):
        return self.__class__({loc: remove_field(data.data(), field_name, new_class) for loc, data in self.items()})

    @classmethod
    def from_fields(cls, dataclass: type[TimeSeriesData], fields: dict[str, 'DataSet[TimeSeriesArray]']):
        start_timestamp = min(data.start_timestamp for data in fields.values())
        end_timestamp = max(data.end_timestamp for data in fields.values())
        period_range = PeriodRange(start_timestamp, end_timestamp, fields[next(iter(fields))].period_range.delta)
        new_dict = {}
        field_names = list(fields.keys())
        #all_locations = {location for field in fields.values() for location in field.keys()}
        common_locations = set.intersection(*[set(field.keys()) for field in fields.values()])
        #for field, data in fields.items():
        #    assert set(data.keys()) == all_locations, (field, all_locations-set(data.keys()))
        for location in common_locations:
            new_dict[location] = dataclass(period_range, **{field: fields[field][location].fill_to_range(start_timestamp, end_timestamp).value for field in field_names})
        return cls(new_dict)


