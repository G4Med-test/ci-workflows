import os
import requests
import glob
import sys
import time

def die(msg):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)

TOKEN = os.getenv("GH_TOKEN")
REPO = os.getenv("REPO")
ORG = os.getenv("ORG")
PROJECT_NUMBER = int(os.getenv("PROJECT_NUMBER"))
API_URL = "https://api.github.com/graphql"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
REST_HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
container_url = f"https://github.com/{REPO}/pkgs/container/{REPO.split('/')[1]}"

# Query: Get Project ID
query_project = '''
query ($org: String!, $number: Int!) {
  organization(login: $org) {
    projectV2(number: $number) {
      id
    }
  }
}
'''
r = requests.post(API_URL, headers=HEADERS, json={
    "query": query_project,
    "variables": {"org": ORG, "number": PROJECT_NUMBER}
})
response_json = r.json()
print("DEBUG project query response:", response_json)
if "data" not in response_json or not response_json["data"]["organization"] or not response_json["data"]["organization"]["projectV2"]:
    die(f"Failed to get project ID for {ORG} project number {PROJECT_NUMBER}. Check project number, token permissions, and org name. Full response: {response_json}")

project_id = response_json["data"]["organization"]["projectV2"]["id"]

# Query: Get Project Fields
query_fields = '''
query($projectId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      fields(first:50) {
        nodes {
          ... on ProjectV2FieldCommon {
            id
            name
          }
        }
      }
    }
  }
}
'''
r = requests.post(API_URL, headers=HEADERS, json={"query": query_fields, "variables": {"projectId": project_id}})
fields_json = r.json()
if "data" not in fields_json or not fields_json["data"]["node"] or not fields_json["data"]["node"]["fields"]:
    die(f"Failed to get fields for project {project_id}. Full response: {fields_json}")

fields = {f["name"]: f["id"] for f in fields_json["data"]["node"]["fields"]["nodes"]}
for required_field in ["Job name", "Macro", "Container", "Status"]:
    if required_field not in fields:
        die(f"Required project field '{required_field}' not found in the project fields: {list(fields.keys())}")

# Query: Get Status options
query_status_opts = '''
query($fieldId: ID!) {
  node(id: $fieldId) {
    ... on ProjectV2SingleSelectField {
      options { id name }
    }
  }
}
'''
r = requests.post(API_URL, headers=HEADERS, json={"query": query_status_opts, "variables": {"fieldId": fields["Status"]}})
status_json = r.json()
if "data" not in status_json or not status_json["data"]["node"] or not status_json["data"]["node"].get("options"):
    die(f"Failed to get Status field options. Full response: {status_json}")
status_opts = {o["name"]: o["id"] for o in status_json["data"]["node"]["options"]}
if "pending" not in status_opts:
    die(f"Status field does not have a 'pending' option. Found: {list(status_opts.keys())}")

macro_files = glob.glob("macro/*.mac")
repo_name = REPO.split('/')[1]

for file_path in macro_files:
    macro_name = os.path.basename(file_path)
    job_name = f"{repo_name}-{macro_name}"
    macro_url = f"https://raw.githubusercontent.com/{REPO}/main/macro/{macro_name}"

    # Create a new Issue
    issue_title = f"Run macro {macro_name}"
    issue_body = f"Job for macro {macro_name}"
    issue_response = requests.post(f"https://api.github.com/repos/{REPO}/issues", headers=REST_HEADERS, json={
        "title": issue_title,
        "body": issue_body
    })
    if issue_response.status_code != 201:
        die(f"Failed to create issue for macro {macro_name}. Response: {issue_response.status_code} {issue_response.text}")
    issue_node_id = issue_response.json()["node_id"]

    # Add Issue to Project
    mutation_add = '''
    mutation($input: AddProjectV2ItemByIdInput!) {
      addProjectV2ItemById(input: $input) {
        item { id }
      }
    }
    '''
    variables_add = {"input": {"projectId": project_id, "contentId": issue_node_id}}
    add_response = requests.post(API_URL, headers=HEADERS, json={"query": mutation_add, "variables": variables_add})
    add_json = add_response.json()
    if "data" not in add_json or not add_json["data"].get("addProjectV2ItemById"):
        die(f"Failed to add issue for macro {macro_name} to project. Response: {add_json}")
    item_id = add_json["data"]["addProjectV2ItemById"]["item"]["id"]

    # Function to set project field value
    mutation_update = '''
    mutation($input: UpdateProjectV2ItemFieldValueInput!) {
      updateProjectV2ItemFieldValue(input: $input) { projectV2Item { id } }
    }
    '''
    def set_field(item_id, field_id, value):
        vars = {"input": {"projectId": project_id, "itemId": item_id, "fieldId": field_id, "value": value}}
        response = requests.post(API_URL, headers=HEADERS, json={"query": mutation_update, "variables": vars})
        result = response.json()
        if "errors" in result:
            die(f"Failed to set field {field_id} for item {item_id}: {result}")

    # Set required fields
    set_field(item_id, fields["Job name"], {"text": job_name})
    set_field(item_id, fields["Macro"], {"text": macro_url})
    set_field(item_id, fields["Container"], {"text": container_url})
    set_field(item_id, fields["Status"], {"singleSelectOptionId": status_opts["pending"]})

    print(f"✅ Added Project entry for {macro_name}")
    # Optional: sleep to avoid rate limits
    time.sleep(1)

print("All macros have been processed.")
