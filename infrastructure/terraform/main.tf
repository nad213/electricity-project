terraform {
  backend "s3" {
    bucket = "electricity-terraform-state"
    key    = "terraform.tfstate"
    region = "eu-west-3"
  }
}

provider "aws" {
  region = "eu-west-3"
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "elecshiny_bucket" {
  bucket = "elec-app-${random_id.suffix.hex}"
}

resource "aws_s3_object" "folder_01_downloaded" {
  bucket = aws_s3_bucket.elecshiny_bucket.bucket
  key    = "01_downloaded/"
}

resource "aws_s3_object" "folder_02_combine" {
  bucket = aws_s3_bucket.elecshiny_bucket.bucket
  key    = "02_clean/"
}



