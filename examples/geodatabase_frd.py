"""
Copyright 2021 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging
import json
import argparse

import apache_beam as beam
from apache_beam.io.gcp.internal.clients import bigquery as beam_bigquery
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions


def format_record(element):
    from osgeo import ogr

    props, geom = element

    ogr_geom = ogr.CreateGeometryFromJson(json.dumps(geom))
    ogr_geom = ogr_geom.MakeValid()

    if ogr_geom is None:
        return None

    return {
        **props,
        'geom': ogr_geom.ExportToJson()
    }


def filter_invalid(element):
    return element is not None


def run(pipeline_args, known_args):
    from geobeam.io import GeodatabaseSource

    pipeline_options = PipelineOptions([
        '--experiments', 'use_beam_bq_sink',
        '--setup_file',  '/dataflow/template/setup.py'
    ] + pipeline_args)

    pipeline_options.view_as(SetupOptions).save_main_session = True

    with beam.Pipeline(options=pipeline_options) as p:
        (p
         | beam.io.Read(GeodatabaseSource(known_args.gcs_url,
             layer_name=known_args.layer_name,
             gdb_name=known_args.gdb_name))
         | 'FormatRecords' >> beam.Map(format_record)
         | 'FilterInvalid' >> beam.Filter(filter_invalid)
         | 'WriteToBigQuery' >> beam.io.WriteToBigQuery(
             beam_bigquery.TableReference(
                 datasetId=known_args.dataset,
                 tableId=known_args.table),
             method=beam.io.WriteToBigQuery.Method.FILE_LOADS,
             custom_gcs_temp_location=known_args.custom_gcs_temp_location,
             write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
             create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER))


if __name__ == '__main__':
    import sys
    from os import path
    dir_path = path.dirname(path.realpath(__file__))
    sys.path.insert(0, path.realpath(path.join(dir_path, '../')))

    logging.getLogger().setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('--gcs_url')
    parser.add_argument('--dataset')
    parser.add_argument('--table')
    parser.add_argument('--layer_name')
    parser.add_argument('--gdb_name')
    parser.add_argument('--in_epsg', type=int, default=None)
    parser.add_argument('--custom_gcs_temp_location')
    known_args, pipeline_args = parser.parse_known_args()

    run(pipeline_args, known_args)