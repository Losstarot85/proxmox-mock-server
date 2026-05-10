.PHONY: help build run stop logs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build the Docker image
	docker compose build

run: ## Start the mock server in the background
	docker compose up -d

stop: ## Stop the mock server
	docker compose down

logs: ## View server logs
	docker compose logs -f

clean: ## Stop and remove containers, networks, and images
	docker compose down --rmi all --volumes
