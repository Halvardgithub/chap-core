import dataclasses
from dataclasses import replace
from typing import Sequence

from bionumpy.bnpdataclass import bnpdataclass

from climate_health.external.models.jax_models.model_spec import Normal, IsDistribution
from climate_health.external.models.jax_models.protoype_annotated_spec import Positive
from climate_health.external.models.jax_models.utii import state_or_param, PydanticTree, get_state_transform

hierarchical = lambda name: state_or_param


@state_or_param
class GlobalParams(PydanticTree):
    alpha: float = 0.
    beta: float = 0.
    sigma: Positive = 1.


@hierarchical('District')
class DistrictParams(PydanticTree):
    alpha: float = 0.
    beta: float = 0.


@bnpdataclass
class Observations:
    x: float
    y: float


def linear_regression(params: GlobalParams, given: Observations) -> IsDistribution:
    y_hat = params.alpha + params.beta * given.x
    return Normal(y_hat, params.sigma)


def join_global_and_district(global_params: GlobalParams, district_params: DistrictParams) -> GlobalParams:
    return replace(global_params,
                   **{field.name: getattr(global_params, field.name) + getattr(district_params, field.name) for field in
                      dataclasses.fields(district_params)})


def hierarchical_linear_regression(global_params: GlobalParams, district_params: dict[DistrictParams],
                                   given: dict[Observations]) -> IsDistribution:
    params = {name: join_global_and_district(global_params, district_params[name]) for name in district_params}
    print(params)
    return {name: linear_regression(params[name], given[name]) for name in district_params}


#def hierarchical_prior(gloabal_params, )


def get_hierarchy_logprob_func(global_params_cls, district_params_cls, observed):
    T_Param, transform, *_ = get_state_transform(global_params_cls)
    T_ParamD, transformD, *_ = get_state_transform(district_params_cls)
    prior = T_Param()
    priorD = T_ParamD()

    def logprob_func(t_params):
        global_params, district_params = t_params
        prior_pdf = prior.log_prob(global_params) + sum(priorD.log_prob(district_params[name]) for name in district_params)
        print('Prior', prior_pdf)
        all_params = transform(global_params), {name: transformD(district_params[name]) for name in district_params}
        models = hierarchical_linear_regression(*all_params, observed)
        obs_pdf = sum(models[name].log_prob(observed[name].y).sum()
                      for name in observed)
        print('Observed', obs_pdf)
        return prior_pdf + obs_pdf
    return logprob_func


def get_logprob_func(params_cls, observed):
    sampled_y = observed.y
    T_Param, transform, inv_transform = get_state_transform(params_cls)
    prior = T_Param()

    def logprob_func(t_params):
        all_params = transform(t_params)
        return prior.log_prob(t_params) + linear_regression(all_params, observed).log_prob(sampled_y).sum()

    return logprob_func


def spatial_type(locations: Sequence[str]):
    pass