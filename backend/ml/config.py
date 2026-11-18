"""Configuration for ML features."""

from pydantic import Field
from pydantic_settings import BaseSettings


class MLConfig(BaseSettings):
    """ML feature configuration with environment variable overrides."""

    # Feature flags
    enable_kalman_filter: bool = True
    enable_anomaly_detection: bool = True
    enable_predictions: bool = True
    enable_slm: bool = False  # Requires model download (~1GB)

    # Kalman filter parameters (tilt_ui-0hic; fitted on measured Tilt noise)
    kalman_process_noise_sg: float = Field(1e-9, gt=0)  # q, SG^2/h^3
    kalman_process_noise_temp: float = Field(0.05, gt=0)  # q, C^2/h^3
    kalman_measurement_noise_sg: float = Field(4e-8, gt=0)  # variance, sigma 2e-4 SG
    kalman_measurement_noise_temp: float = Field(0.0225, gt=0)  # variance, sigma 0.15 C
    # iSpindel / GravityMon / RAPT: angle-derived SG is noisier. Assumed
    # sigma 1e-3 SG, not measured; retune when such a device logs a batch.
    kalman_measurement_noise_sg_angle: float = Field(1e-6, gt=0)

    # Predictions
    prediction_min_readings: int = 10
    prediction_completion_threshold: float = 0.002  # SG/day


    # SLM parameters
    slm_model_path: str = "~/.cache/llm/ministral-3b-instruct-q4_k_m.gguf"  # Mistral Ministral 3B
    slm_max_tokens: int = 256
    slm_context_size: int = 2048

    class Config:
        env_prefix = "TILT_ML_"
