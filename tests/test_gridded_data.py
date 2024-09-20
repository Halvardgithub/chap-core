import pytest

from climate_health.google_earth_engine.gee_raw import load_credentials

@pytest.fixture
def credentials():
    try:
        load_credentials()
    except Exception as e:
        pytest.skip("Credentials not found")

@pytest.fixture
def polygons_filename(data_path):
    return data_path/'philippines_polygons.json'

@pytest.skip("Not implemented")
def test_get_gridded_data(polygons_filename):
    from climate_health.climate_data.gridded_data import get_gridded_data
    get_gridded_data(polygons_filename)
