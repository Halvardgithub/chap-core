from typing import Any

from climate_health.external.models.jax_models.jax import jnp
from climate_health.external.models.jax_models.model_spec import IsDistribution, Poisson, expit, DictDist, Normal, \
    SSMForecasterNuts, NutsParams


class NaiveSSM:
    global_params = ['beta_temp']
    state_params = ['logit_infected']
    location_params = ['logit_infected_decay', 'log_observation_rate']
    predictors = ['mean_temperature']

    def observation_distribution(self, state: dict[str, Any], params: dict[str, Any]) -> IsDistribution:
        return Poisson(jnp.exp(state['logit_infected'] + params['log_observation_rate']))

    def _temperature_effect(self, temperature: float, params: dict[str, Any]) -> float:
        return params['beta_temp'] * temperature

    def state_distribution(self, previous_state: dict, params: dict[str, Any], observed: dict) -> IsDistribution:
        mu = previous_state['logit_infected'] * expit(params['logit_infected_decay']) + self._temperature_effect(
            observed['mean_temperature'], params)
        return DictDist({'logit_infected': Normal(mu, 1.0)})


class NaiveModel(SSMForecasterNuts):
    def __init__(self):
        spec = NaiveSSM()
        params = NutsParams(n_warmup=100, n_samples=100)
        super().__init__(spec, params)