import datetime
import json
import logging
from typing import Iterable, List, Callable
from dotenv import find_dotenv, load_dotenv
import ee
import os
import zipfile
import pandas as pd
from pydantic import BaseModel
from climate_health.datatypes import Location, ClimateData, SimpleClimateData
from climate_health.datatypes import ClimateData
from climate_health.spatio_temporal_data.temporal_dataclass import SpatioTemporalDict
from climate_health.time_period.date_util_wrapper import PeriodRange, TimePeriod
from typing import List
import ee

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def meter_to_mm(m):
    return round(m * 1000, 3)

def kelvin_to_celsium(v):
    return round(v - 273.15, 2)

class Band(BaseModel):
    class Config():
        arbitrary_types_allowed=True

    name: str
    reducer: str
    converter: Callable
    indicator : str
    periode_reducer : str

bands = [
    Band(name="temperature_2m", reducer="mean", periode_reducer="mean", converter=kelvin_to_celsium, indicator = "mean_temperature"),
    Band(name="total_precipitation_sum", reducer="mean", periode_reducer="sum", converter=meter_to_mm, indicator = "rainfall")
]


class Periode(BaseModel):
    class Config():
        arbitrary_types_allowed=True

    id: str
    startDate : datetime.datetime
    endDate : datetime.datetime



class Era5LandGoogleEarthEngineHelperFunctions():


    
    #Get every dayli image that exisist within a periode, and reduce it to a periodeReducer value
    def get_image_for_period(self, p : Periode, band : Band, collection : ee.ImageCollection) -> ee.Image:
        p = ee.Dictionary(p)
        start = ee.Date(p.get("start_date"))
        end = ee.Date(p.get("end_date"))#.advance(-1, "day") #remove one day, since the end date is inclusive on current format?

        #Get only images from start to end, for one bands
        filtered : ee.ImageCollection = collection.filterDate(start, end).select(band.name)

        #Aggregate the imageCollection to one image, based on the periodeReducer
        return getattr(filtered, band.periode_reducer)() \
            .set("system:period", p.get("period")) \
            .set("system:time_start", start.millis()) \
            .set("system:time_end", end.millis()) \
            .set("system:indicator", band.indicator)


    def create_ee_dict(self, p : TimePeriod):
        return ee.Dictionary({"period" : p.id, "start_date" : p.start_timestamp.date, "end_date" : p.end_timestamp.date})
        
    def creat_ee_feature(self, feature, image, eeReducerType):
        return ee.Feature(
            None, #exlude geometry
            {
                'ou': feature.id(),
                'period': image.get('system:period'),
                'value' : feature.get(eeReducerType),
                'indicator' : image.get('system:indicator')
            }
        )
    
    def convert_value_by_band_converter(self, data, bands : List[Band]):
        return [{**f['properties'],
                    #Using the right converter on the value, based on the whats defined as band-converter
                    **{'value': next(b.converter for b in bands if f['properties']['indicator'] == b.indicator)(f['properties']['value'])}}
                for f in data]
    
    def feature_collection_to_list(self, feature_collection : 'ee.FeatureCollection'):
        size = feature_collection.size().getInfo()
        result : List = []
        take = 5_000

        #Keeps every f.properties, and replace the band values with the converted values
        for i in range(0, size, take):     
            result = result + (feature_collection.toList(take, i).getInfo())
            logger.log(logging.INFO, f" Fetched {i+take} of {size}")

        return result
    
    @staticmethod
    def parse_gee_properties(property_dicts: list[dict])->SpatioTemporalDict:
        df = pd.DataFrame(property_dicts)
        location_groups = df.groupby('ou')
        full_dict = {}
        for location, group in location_groups:
            data_dict, pr = Era5LandGoogleEarthEngineHelperFunctions._get_data_dict(group)
            full_dict[location] = SimpleClimateData(pr, **data_dict)
        return SpatioTemporalDict(full_dict)

    @staticmethod
    def _get_data_dict(group):
        data_dict = {band: group[group['indicator'] == band] for band in group['indicator'].unique()}
        pr = None
        for band, band_group in group.groupby('indicator'):
            data_dict[band] = band_group['value']
            pr = PeriodRange.from_ids(band_group['period'])
        return data_dict, pr

    @staticmethod
    def gee_properties_to_fields(property_dicts: list[dict]) -> dict[str, SpatioTemporalDict]:
        df = pd.DataFrame(property_dicts)
        location_groups = df.groupby('ou')
        #field_dict = {name: {} for name in}
        #for location, group in location_groups:
        #    data_dict, pr = Era5LandGoogleEarthEngineHelperFunctions._get_data_dict(group)


class Era5LandGoogleEarthEngine():
    
    def __init__(self):
        self.gee_helper = Era5LandGoogleEarthEngineHelperFunctions()
        self.is_initialized = False
        self._initialize_client()

    def _initialize_client(self):
        load_dotenv(find_dotenv())
        #read environment variables
        account = os.environ.get('GOOGLE_SERVICE_ACCOUNT_EMAIL')
        private_key = os.environ.get('GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY')

        if(not account):
            logger.warn("GOOGLE_SERVICE_ACCOUNT_EMAIL is not set, you need to set it in the environment variables to use Google Earth Engine")
        if(not private_key):
            logger.warn("GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY is not set, you need to set it in the environment variables to use Google Earth Engine")

        if(not account or not private_key):
            return
        
        try:
            credentials = ee.ServiceAccountCredentials(account, key_data=private_key)
            ee.Initialize(credentials)
            logger.info("Google Earth Engine initialized, with account: "+account)
            self.is_initialized = True
        except ValueError as e:
            logger.error(e)

    def get_historical_era5(self, features, periodes : Iterable[TimePeriod]):
        
        ee_reducer_type = "mean"

        collection = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR').select([band.name for band in bands])
        feature_collection : ee.FeatureCollection = ee.FeatureCollection(features)

        #Creates a ee.List for every periode, containing id (periodeId), start_date and end_date for each period
        periode_list = ee.List([self.gee_helper.create_ee_dict(p) for p in periodes])
    
        ee_scale = collection.first().select(0).projection().nominalScale()
        eeReducer = getattr(ee.Reducer, ee_reducer_type)()

        daily_collection = ee.ImageCollection([])

        #Map the bands, then the periodeList for each band, and return the aggregated Image to the ImageCollection
        for b in bands:
            daily_collection = daily_collection.merge(ee.ImageCollection.fromImages(
                periode_list.map(lambda period : self.gee_helper.get_image_for_period(period, b, collection))
            ).filter(ee.Filter.listContains("system:band_names", b.name)))  # Remove empty images

        #Reduce the result, to contain only, orgUnitId, periodeId and the value
        reduced = daily_collection.map(lambda image: 
            image.reduceRegions(
                collection=feature_collection,
                reducer=eeReducer,
                scale=ee_scale
            ).map(lambda feature: 
                self.gee_helper.creat_ee_feature(feature, image, ee_reducer_type)
            )
        ).flatten()

        feature_collection : ee.FeatureCollection = ee.FeatureCollection(reduced)

        result = self.gee_helper.feature_collection_to_list(feature_collection)
        parsed_result = self.gee_helper.convert_value_by_band_converter(result, bands)
        
        return self.gee_helper.parse_gee_properties(parsed_result)












        