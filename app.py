from __future__ import annotations

import fnmatch

import os
from json import dumps
from tempfile import TemporaryDirectory
from typing import Any, List, Union, Dict, Generator

import pdal
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel, Json
import boto3
from fastapi.openapi.docs import get_swagger_ui_html

class Files(BaseModel):
    files: List[str]

class Mask(BaseModel):
    mask: str

class Task(BaseModel):
    pipeline: List[Dict[str, Union[str, List[str]]]]
    input: Union[Files, Mask]
    output: Union[Files, Mask]

app = FastAPI(openapi_url='/swagger.json')

s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=os.environ.get('AWS_DEFAULT_REGION'),
    endpoint_url=os.environ.get('AWS_ENDPOINT_URL')
)

def replace_pipeline_filenames(stg: Dict[str, str], input_filename, output_filename: str) -> Dict[str, str]:
    readers_formats = ['readers.gdal', 'readers.las', 'readers.text']
    writers_formats = ['writers.text']
    if stg['type'] in readers_formats:
        stg['filename'] = input_filename
    if stg['type'] in writers_formats:
        stg['filename'] = output_filename
    return stg

def replace_filename_ending(filename, old, new):
    if filename.endswith(old):
        base = filename[:-len(old)]
        return f'{base}{new}'
    return filename

def list_files_with_pattern(bucket_name, pattern):
    subfolder, filepattern = pattern.rsplit('/', maxsplit=1)
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=subfolder + '/')

    if 'Contents' not in response:
        print(f"No files found in bucket '{bucket_name}'.")
        return

    return [f"s3://{bucket_name}/{obj['Key']}" for obj in response['Contents'] if fnmatch.fnmatch(obj['Key'], pattern)]



@app.post('/api/v1/kruti/')
async def kruti(
        task: Task,
                ) :
    input_filename = 'input.pedal'
    output_filename = 'outputfile.pedal'
    filenames = []
    try:
        with TemporaryDirectory() as tempdir:
            input_path = os.path.join(tempdir, input_filename)
            output_path = os.path.join(tempdir, output_filename)

            files = []

            if isinstance(task.input, Files):
                files = task.input.files
            elif isinstance(task.input, Mask):
                bucket, pattern = task.input.mask[5:].split('/', 1)
                _, ext = pattern.split('.', 1)
                ext = '.' + ext
                files = list_files_with_pattern(bucket, pattern)

            for idx, file in enumerate(files):
                # Parse bucket and key
                s3_uri = file[5:]
                bucket, key = s3_uri.split('/', 1)
                s3_client.download_file(bucket, key, input_path)

                # replace all filenames with predefined one
                payload = dumps([replace_pipeline_filenames(stg, input_path, output_path) for stg in task.pipeline])

                pipeline = pdal.Pipeline(payload)
                pipeline.execute()

                output_key = ''
                if isinstance(task.output, Files):
                    output_key = task.output.files[idx][5:]
                elif isinstance(task.output, Mask):
                    output_key = replace_filename_ending(key, ext, task.output.mask)

                s3_client.upload_file(output_path, bucket, output_key)
                filenames.append(output_key)
        return {"filenames": filenames}
    except Exception as e:
        print(pipeline.log)
        print(e)

@app.get('/docs', include_in_schema=False)
def custom_swagger_ui_html():
    return get_swagger_ui_html(openapi_url=app.openapi_url, title="Swagger UI")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get('UVICORN_HOST', '0.0.0.0'), port=os.environ.get('UVICORN_PORT', 8080), log_level=os.environ.get('LOG_LEVEL', 'INFO'))