#!/usr/bin/env python3
"""
OpenAI MCP Integration Example

Example showing how to use OpenAI's MCP tool with our F1 telemetry server.
This demonstrates the exact API calls needed for MCP integration.
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# OpenAI API configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/responses"

# Your F1 telemetry MCP server URL (when running the HTTP server)
F1_MCP_SERVER_URL = "http://localhost:8000/mcp"

def call_openai_with_f1_mcp(user_message: str):
    """
    Call OpenAI API with F1 telemetry MCP integration
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    payload = {
        "model": "gpt-4o",
        "tools": [
            {
                "type": "mcp",
                "server_label": "f1-telemetry",
                "server_description": "F1 telemetry data server providing live race information, driver standings, and car telemetry",
                "server_url": F1_MCP_SERVER_URL,
                "require_approval": "never",  # Auto-approve all F1 telemetry tools
                "allowed_tools": [
                    "get_session_info",
                    "get_race_standings", 
                    "get_player_telemetry",
                    "get_recent_events",
                    "get_race_summary"
                ]
            }
        ],
        "input": user_message
    }
    
    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling OpenAI API: {e}")
        return None

def example_f1_queries():
    """
    Example F1 race engineer queries using MCP
    """
    queries = [
        "What's my current position and how am I doing in the race?",
        "Check my fuel levels and tire wear - do I need to pit soon?", 
        "Who's leading the race and what are the gaps?",
        "Any recent penalties or incidents I should know about?",
        "Give me a complete race strategy analysis based on current conditions"
    ]
    
    print("🏎️  F1 Race Engineer - OpenAI MCP Integration Examples")
    print("=" * 60)
    
    for i, query in enumerate(queries, 1):
        print(f"\n{i}. Query: {query}")
        print("-" * 40)
        
        response = call_openai_with_f1_mcp(query)
        
        if response:
            # Extract the assistant's response
            if 'choices' in response and response['choices']:
                assistant_message = response['choices'][0].get('message', {}).get('content', 'No response')
                print(f"🏁 Race Engineer: {assistant_message}")
                
                # Show any MCP tool calls that were made
                if 'tool_calls' in response['choices'][0].get('message', {}):
                    print("\n📊 Telemetry Data Used:")
                    for tool_call in response['choices'][0]['message']['tool_calls']:
                        if tool_call.get('type') == 'mcp_call':
                            print(f"  - {tool_call.get('name', 'Unknown tool')}")
            else:
                print("❌ No response received")
        else:
            print("❌ Failed to get response")
        
        print("\n" + "=" * 60)

def interactive_f1_engineer():
    """
    Interactive F1 race engineer using OpenAI MCP
    """
    print("🏎️  Interactive F1 Race Engineer")
    print("Ask me anything about the current race!")
    print("Type 'quit' to exit\n")
    
    while True:
        user_input = input("🎤 Your question: ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("👋 Arrivederci! Good racing!")
            break
            
        if not user_input:
            continue
            
        print("🔄 Checking telemetry...")
        
        response = call_openai_with_f1_mcp(user_input)
        
        if response and 'choices' in response and response['choices']:
            assistant_message = response['choices'][0].get('message', {}).get('content', 'No response')
            print(f"\n🏁 Race Engineer: {assistant_message}\n")
        else:
            print("❌ Sorry, I'm having trouble accessing the telemetry data.\n")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        interactive_f1_engineer()
    else:
        example_f1_queries()