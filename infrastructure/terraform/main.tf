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
  bucket       = aws_s3_bucket.elecshiny_bucket.bucket
  key          = "01_downloaded/"
}

resource "aws_s3_object" "folder_02_combine" {
  bucket       = aws_s3_bucket.elecshiny_bucket.bucket
  key          = "02_clean/"
}


resource "aws_s3_object" "folder_99_params" {
  bucket       = aws_s3_bucket.elecshiny_bucket.bucket
  key          = "99_params/"
}

#upload of the file containing the list of urls to download
resource "aws_s3_object" "filelist_csv" {
  bucket       = aws_s3_bucket.elecshiny_bucket.bucket
  key          = "99_params/filelist.csv"
  source       = "./99_params/filelist.csv"
  etag         = filemd5("./99_params/filelist.csv") 
}

