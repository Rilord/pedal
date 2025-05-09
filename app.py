import os
from json import dumps
from tempfile import TemporaryDirectory
from typing import Any, List, Union, Dict, Generator

import pdal
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel, Json
import boto3
from urllib.request import urlretrieve


class Task(BaseModel):
    pipeline: List[Dict[str, str]]
    file_uri: str

app = FastAPI(openapi_url='/swagger.json')

s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=os.environ.get('AWS_DEFAULT_REGION'),
    endpoint_url=os.environ.get('AWS_ENDPOINT_URL')
)

def replace_filenames(stg: Dict[str, str], input_filename, output_filename: str) -> Dict[str, str]:
    readers_formats = ['readers.gdal', 'readers.las', 'readers.text']
    writers_formats = ['writers.text']
    if stg['type'] in readers_formats:
        stg['filename'] = input_filename
    if stg['type'] in writers_formats:
        stg['filename'] = output_filename
    return stg

@app.post('/api/v1/kruti/')
async def kruti(
        task: Task,
                ) -> dict[str, str]:
    input_filename = 'input.pedal'
    output_filename = 'outputfile.pedal'
    try:
        with TemporaryDirectory() as tempdir:
            input_path = os.path.join(tempdir, input_filename)
            output_path = os.path.join(tempdir, output_filename)
            if task.file_uri.startswith('s3://'):
                # Parse bucket and key
                s3_uri = task.file_uri[5:]
                bucket, task_uuid, batch_id, key = s3_uri.split('/', 3)
                s3_client.download_file(bucket, f"{task_uuid}/{batch_id}/{key}", input_path)
            else:
                urlretrieve(task.file_uri, input_path)
            payload = dumps([replace_filenames(stg, input_path, output_path) for stg in task.pipeline])
            pipeline = pdal.Pipeline(payload)
            pipeline.execute()
            if task.file_uri.startswith('s3://'):
                output_bucket = bucket
                output_key = f"{task_uuid}/{batch_id}/{output_filename}"
                s3_client.upload_file(output_path, output_bucket, output_key)
                return {"filename": output_key}
    except Exception as e:
        print(pipeline.log)
        print(e)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8080, log_level="debug")