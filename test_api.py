"""Test script to demonstrate OpenTelemetry tracing."""

import httpx

from foreman.telemetry import setup_telemetry

# Setup telemetry (in production, this would point to a real collector like Jaeger)
# For this demo, we'll just configure it without an exporter
setup_telemetry(service_name="foreman-test-client")

print("Testing Foreman API with OpenTelemetry instrumentation...")
print("-" * 60)

# Create a client
with httpx.Client(base_url="http://localhost:8000") as client:
    # Test health check
    print("\n1. Testing health check endpoint...")
    response = client.get("/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")

    # Create a request
    print("\n2. Creating an image generation request...")
    request_data = {
        "prompt": "A futuristic city at night with neon lights",
        "model": "stable-diffusion-v1",
        "width": 1024,
        "height": 768,
        "num_images": 3,
    }
    response = client.post("/requests", json=request_data)
    print(f"   Status: {response.status_code}")
    result = response.json()
    print(f"   Request ID: {result['id']}")
    print(f"   Status: {result['status']}")

    request_id = result["id"]

    # Get the request
    print("\n3. Retrieving the request...")
    response = client.get(f"/requests/{request_id}")
    print(f"   Status: {response.status_code}")
    request_details = response.json()
    print(f"   Prompt: {request_details['prompt']}")
    print(f"   Size: {request_details['width']}x{request_details['height']}")
    print(f"   Num Images: {request_details['num_images']}")

    # Update status
    print("\n4. Updating request status...")
    response = client.put(f"/requests/{request_id}/status?new_status=processing")
    print(f"   Status: {response.status_code}")
    print(f"   Message: {response.json()['message']}")

    # List all requests
    print("\n5. Listing all requests...")
    response = client.get("/requests")
    print(f"   Status: {response.status_code}")
    requests = response.json()
    print(f"   Total requests: {len(requests)}")

print("\n" + "-" * 60)
print("All API tests completed successfully!")
print("\nNote: OpenTelemetry is instrumented and would send traces to")
print("an OTLP endpoint if OTEL_EXPORTER_OTLP_ENDPOINT is configured.")
print("Try running with docker-compose to see tracing in Jaeger UI.")
