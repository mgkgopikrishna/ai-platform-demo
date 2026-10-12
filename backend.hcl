# Shared remote-state settings for every team stack.
# Each stack adds its own key at init time, so state is isolated per team.
bucket         = "REPLACE-ME-tf-state"
region         = "us-east-1"
dynamodb_table = "REPLACE-ME-tf-locks"
encrypt        = true
