from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongo_uri: str
    db_name: str = "asana_sense"
    poses_collection: str = "poses"

    model_path: str = "model_files/extra_trees_pose_model.pkl"
    label_encoder_path: str | None = "model_files/label_encoder.pkl"
    confidence_threshold: float = 0.6

    class Config:
        env_file = ".env"


settings = Settings()
