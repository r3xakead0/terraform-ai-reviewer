.PHONY: sync test lint fmt-check terraform-validate plan scan review-fixture demo-change

sync:
	uv sync --locked --all-groups

test:
	uv run pytest

lint:
	uv run ruff check .

fmt-check:
	terraform -chdir=demo/terraform fmt -check -recursive
	terraform -chdir=bootstrap fmt -check -recursive

terraform-validate:
	terraform -chdir=demo/terraform init -backend=false -input=false
	terraform -chdir=demo/terraform validate
	terraform -chdir=bootstrap init -backend=false -input=false
	terraform -chdir=bootstrap validate

plan:
	mkdir -p .artifacts
	AWS_ACCESS_KEY_ID=terraform-reviewer-demo AWS_SECRET_ACCESS_KEY=terraform-reviewer-demo terraform -chdir=demo/terraform plan -input=false -lock=false -no-color -out=../../.artifacts/tfplan > /dev/null
	terraform -chdir=demo/terraform show -json ../../.artifacts/tfplan > .artifacts/tfplan.json

scan:
	mkdir -p .artifacts
	uv run checkov -f .artifacts/tfplan.json --repo-root-for-plan-enrichment demo/terraform --deep-analysis --soft-fail --quiet -o json > .artifacts/checkov.json

review-fixture:
	mkdir -p .artifacts
	uv run terraform-ai-review review --plan fixtures/tfplan.json --checkov fixtures/checkov.json --provider fixture --fixture fixtures/bedrock-response.json --config reviewer.yaml --json-out .artifacts/review.json --markdown-out .artifacts/review.md

demo-change:
	git apply --check demo/scenarios/risky.patch
	git apply demo/scenarios/risky.patch
