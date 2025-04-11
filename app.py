from flask import Flask, jsonify, request
from urllib.parse import urlparse

import requests
import base64
import csv
import io
import json
import os

APP_NAME = "afterlife-variables-creator"
GITLAB_URL = 'https://<<GITLAB_NAME>>/api/v4'
PRIVATE_TOKEN = 'xxxxxxxxxxxxxxxxx'
CSV_GENERATE_PATH='C:\\Development\\Repositories\\afterlife-variables-creator\\csv\\'

VARIABLES = [{
    'key': 'CRITICAL_PROJECT',
    'value': 'true'
}]

__version__ = "0.0.1"

app = Flask(__name__)


@app.route('/health/readiness', methods=['GET'])
def healthcheckReadiness():
    return jsonify(status=200, message="Ready"), 200


@app.route('/health/liveness', methods=['GET'])
def healthcheckLiveness():
    return jsonify(status=200, message="Live"), 200


@app.route(f'/{APP_NAME}/execute', methods=['POST'])
def markerExecute():
    repositories_to_marker_csv_file = request.files['repositories_to_marker']
    token_decoded_gitlab = base64.b64decode(PRIVATE_TOKEN)
    result_create_variables = createVariables(
        token_decoded_gitlab, repositories_to_marker_csv_file)
    if result_create_variables != "All repositories were marked!":
        return jsonify(status=500, message=result_create_variables), 500
    else:
        return jsonify(status=200, message=result_create_variables), 200

def searchMetaData(token_decoded_gitlab,  project_name_csv, project_group_csv, fai_id_csv):

    page_response_gitlab = 0

    url_search_gitlab = f'{GITLAB_URL}/projects?search={project_name_csv}'
    response_gitlab = requests.get(url_search_gitlab, headers={
        'Private-Token': token_decoded_gitlab}, params={'page': page_response_gitlab, 'per_page': 100} )
    total_pages_response_gitlab = int(response_gitlab.headers.get('X-Total-Pages', 0))
    
    while True:
    
        if response_gitlab.status_code == 200:

            response_gitlab_json = response_gitlab.json()

            for repository in response_gitlab_json:

                repository_project_id = repository.get("id")
                repository_project_path_with_namespace  = repository.get(
                    "path_with_namespace")
                repository_project_path_csv = project_group_csv +"/"+ project_name_csv

                if repository_project_path_csv == repository_project_path_with_namespace:

                    url_search_gitlab = f'{GITLAB_URL}/projects/{repository_project_id}/labels'
                    response_gitlab = requests.get(url_search_gitlab, headers={
                        'Private-Token': token_decoded_gitlab})
                    
                    if response_gitlab.status_code == 200:

                        response_gitlab_json = response_gitlab.json()
                        application_id_labels_exists = [label for label in response_gitlab_json if label["name"] == "application-id" and label["description"] == fai_id_csv]
                        
                        if len(application_id_labels_exists) > 0:
                            metadata = {"repository_project_id": repository_project_id, "web_url": repository.get(
                                "web_url"), "application_id_labels": application_id_labels_exists, "status": "OK", "message": "APPLICATION-ID FOUND"}
                            print("Metadata found (JSON FORMAT): " +
                                  json.dumps(metadata))
                            return metadata
                        else:
                            metadata = {"status": "ERROR", "message": "APPLICATION-ID NOT FOUND"}
                            return metadata
                    else:
                        error = f'Unexpected error in search labels in {project_name_csv} with id {repository_project_id}, details: status_code; {response_gitlab.status_code} - response; {response_gitlab.text}!'
                        print(error)
                        metadata = {"status": "ERROR", "message": error.upper()}
                        return metadata
        else:
            error = f'Unexpected error in search repository project id {project_name_csv}, details: status_code; {response_gitlab.status_code} - response; {response_gitlab.text}!'
            print(error)
            metadata = {"status": "ERROR", "message": error.upper()}
            return metadata
    
        if page_response_gitlab == total_pages_response_gitlab:
            break

        page_response_gitlab +=1

        response_gitlab = requests.get(url_search_gitlab, headers={
        'Private-Token': token_decoded_gitlab}, params={'page': page_response_gitlab, 'per_page': 100} )


def createVariables(token_decoded_gitlab, repositories_to_marker_csv_file):
    try:

        file_stream = io.StringIO(repositories_to_marker_csv_file.read().decode('utf-8'))
        csv_reader = csv.reader(file_stream)
        rows = list(csv_reader)

        new_column = 'Result'
        header = rows[0]
        if new_column not in header:
            header.append(new_column)

        for row in rows[1:]:

            result = ""
            project_url_csv = (urlparse(row[0]).path).strip('/').split('/')
            project_group_csv = '/'.join(project_url_csv[:-1])
            project_name_csv = project_url_csv[-1]
            fai_id_csv = row[1]

            print("-----------------------------------------------------")
            print(f'Searching metadata of repository: {project_name_csv}')

            project_metadata = searchMetaData(
                token_decoded_gitlab, project_name_csv, project_group_csv, fai_id_csv)
            
            try:

                if project_metadata.get("status") == "ERROR" and project_metadata.get("message") != "APPLICATION-ID NOT FOUND":
                    result = project_metadata.get("message")
                    print(result)
                    row.append(result)

                if project_metadata.get("status") == "OK" and project_metadata.get("message") == "APPLICATION-ID FOUND":
                    url_variables_gitlab = f'{GITLAB_URL}/projects/{project_metadata.get("repository_project_id")}/variables'
                    response_gitlab = requests.get(url_variables_gitlab, headers={
                        'Private-Token': token_decoded_gitlab}, params={'page': 0, 'per_page': 100})
                    if response_gitlab.status_code == 200:
                        response_gitlab_json = response_gitlab.json()
                        for variable_to_add in VARIABLES:
                            variable_exists = [
                                variable for variable in response_gitlab_json if variable["key"] == variable_to_add.get("key")]
                            if len(variable_exists) == 0:
                                response_gitlab = requests.post(url_variables_gitlab, headers={
                                    'Private-Token': token_decoded_gitlab}, data=variable_to_add)
                                if response_gitlab.status_code == 201:
                                    result = f'The variable {variable_to_add.get("key")} was created in {project_name_csv} ({project_metadata.get("web_url")}) successfully!'
                                    print(result)
                                    row.append(result)
                                else:
                                    result = f'Unexpected error creating variable {variable_to_add.get("key")} in {project_name_csv} -  ({project_metadata.get("web_url")}), details: status_code; {response_gitlab.status_code} - response; {response_gitlab.text}!'
                                    print(result)
                                    row.append(result)
                            else:
                                result = f'The variable {variable_to_add.get("key")} already exists in {project_name_csv} ({project_metadata.get("web_url")})!'
                                print(result)
                                row.append(result)
                    else:
                        result = f'Unexpected error in search variables {project_name_csv} ({project_metadata.web_url}), details: status_code; {response_gitlab.status_code} - response; {response_gitlab.text}!'
                        print(result)
                        row.append(result)
                else:
                    result = f'The label application-id {fai_id_csv} not exists in {project_name_csv} ({project_metadata.get("web_url")})!'
                    print(result)
                    row.append(result)
            except AttributeError:
                result = f'The repository {project_name_csv} was not found!'
                print(result)
                row.append(result)
            
        file_path = os.path.join(CSV_GENERATE_PATH, 'repositories_to_marker_output.csv')
        repositories_to_marker_csv_file.save(file_path)

        with open(file_path, mode='w', newline='', encoding='utf-8') as output_file:
            csv_writer = csv.writer(output_file)
            csv_writer.writerow(header)
            csv_writer.writerows(rows[1:])

        return "All repositories were marked!"

    except Exception as e:
        return f"Unexpected error: {e}!"


app.run(host='127.0.0.1', port=8080)