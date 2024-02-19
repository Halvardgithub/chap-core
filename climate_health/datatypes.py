import bionumpy as bnp
import pandas as pd
from pydantic import BaseModel, validator

from .file_io import parse_periods_strings
import dataclasses

from .time_period import TimePeriod, Day, Month, Year
from .time_period.dataclasses import Period


@bnp.bnpdataclass.bnpdataclass
class TimeSeriesData:
    time_period: Period

    def topandas(self):
        data_dict = {field.name: getattr(self, field.name) for field in dataclasses.fields(self)}
        data_dict['time_period'] = self.time_period.topandas()
        return pd.DataFrame(data_dict)

    to_pandas = topandas

    def to_csv(self, csv_file: str, **kwargs):
        """Write data to a csv file."""
        data = self.to_pandas()
        data.to_csv(csv_file, index=False, **kwargs)

    @classmethod
    def from_pandas(cls, data):
        time = parse_periods_strings(data.time_period.astype(str))
        variable_names = [field.name for field in dataclasses.fields(cls) if field.name != 'time_period']

        return cls(time, **{name: data[name] for name in variable_names})

    @classmethod
    def from_csv(cls, csv_file: str, **kwargs):
        """Read data from a csv file."""
        data = pd.read_csv(csv_file, **kwargs)
        return cls.from_pandas(data)


@bnp.bnpdataclass.bnpdataclass
class ClimateHealthTimeSeries(TimeSeriesData):
    rainfall: float
    mean_temperature: float
    disease_cases: int

    def todict(self):
        d = super().todict()
        d['time_period'] = self.time_period.topandas()
        return d


@bnp.bnpdataclass.bnpdataclass
class LocatedClimateHealthTimeSeries(ClimateHealthTimeSeries):
    location: str


@bnp.bnpdataclass.bnpdataclass
class ClimateData(TimeSeriesData):
    rainfall: float
    mean_temperature: float
    max_temperature: float

class ClimateHealthTimeSeriesModel(BaseModel):
    time_period: str | pd.Period
    rainfall: float
    mean_temperature: float
    disease_cases: int

    class Config:
        arbitrary_types_allowed = True

    @validator('time_period')
    def parse_time_period(cls, data: str | pd.Period) -> pd.Period:
        if isinstance(data, pd.Period):
            return data
        else:
            return pd.Period(data)


class LocatedClimateHealthTimeSeriesModel(BaseModel):
    time_period: Period
    rainfall: float
    mean_temperature: float
    location: str
    disease_cases: int


class Shape:
    pass

@dataclasses.dataclass
class Location(Shape):
    latitude: float
    longitude: float