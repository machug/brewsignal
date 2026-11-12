"""Configuration for ML features."""

from pydantic_settings import BaseSettings


class MLConfig(BaseSettings):
    """ML feature configuration with environment variable overrides."""

    # Feature flags
    enable_kalman_filter: bool = True
    enable_anomaly_detection: bool = True
    enable_predictions: bool = True
    enable_slm: bool = False  # Requires model download (~1GB)

    # Kalman filter parameters
    kalman_process_noise_sg: float = 1e-8
    kalman_process_noise_temp: float = 0.01
    kalman_measurement_noise_sg: float = 1e-6
    kalman_measurement_noise_temp: float = 0.1

    # Predictions
    prediction_min_readings: int = 10
    prediction_completion_threshold: float = 0.002  # SG/day


    # SLM parameters
    slm_model_path: str = "~/.cache/llm/ministral-3b-instruct-q4_k_m.gguf"  # Mistral Ministral 3B
    slm_max_tokens: int = 256
    slm_context_size: int = 2048

    class Config:
        env_prefix = "TILT_ML_"
