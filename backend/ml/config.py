"""Configuration for ML features."""

from functools import partial

from pydantic import Field

Noise = partial(Field, gt=0, allow_inf_nan=False)
from pydantic_settings import BaseSettings


class MLConfig(BaseSettings):
    """ML feature configuration with environment variable overrides."""

    # Feature flags
    enable_kalman_filter: bool = True
    enable_anomaly_detection: bool = True
    enable_predictions: bool = True
    enable_slm: bool = False  # Requires model download (~1GB)

    # Kalman filter parameters (tilt_ui-0hic; fitted on measured Tilt noise)
    kalman_process_noise_sg: float = Noise(1e-9)  # q, SG^2/h^3
    kalman_process_noise_temp: float = Noise(0.05)  # q, C^2/h^3
    kalman_measurement_noise_sg: float = Noise(4e-8)  # variance, sigma 2e-4 SG
    kalman_measurement_noise_temp: float = Noise(0.0225)  # variance, sigma 0.15 C
    # iSpindel / GravityMon / RAPT: angle-derived SG is noisier. Assumed
    # sigma 1e-3 SG, not measured; retune when such a device logs a batch.
    kalman_measurement_noise_sg_angle: float = Noise(1e-6)

    # Predictions
    prediction_min_readings: int = 10
    prediction_completion_threshold: float = 0.002  # SG/day


    # SLM parameters
    slm_model_path: str = "~/.cache/llm/ministral-3b-instruct-q4_k_m.gguf"  # Mistral Ministral 3B
    slm_max_tokens: int = 256
    slm_context_size: int = 2048

    class Config:
        env_prefix = "TILT_ML_"
