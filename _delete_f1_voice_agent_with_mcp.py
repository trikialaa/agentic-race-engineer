#!/usr/bin/env python3
"""
F1 Voice Agent with MCP Integration

Enhanced F1 race engineer that can access live telemetry data through OpenAI's MCP tool integration.
This agent combines voice interaction with real-time F1 data for intelligent race engineering.
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, List, Optional

import openai
import requests
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class F1RaceEngineerWithMCP:
    """F1 Race Engineer with MCP telemetry integration"""
    
    def __init__(self, mcp_server_url: str = "http://localhost:8000"):
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.mcp_server_url = mcp_server_url
        self.conversation_history = []
        
        # F1 Race Engineer personality and instructions
        self.system_instructions = """
You are an expert Formula 1 race engineer with an Italian accent and personality. 
You have access to live telemetry data from the F1 car and can provide:

- Real-time race strategy advice
- Tire management recommendations  
- Fuel strategy guidance
- Performance analysis and setup advice
- Race position and timing information
- Weather and track condition updates
- Damage assessment and pit stop recommendations

Always speak with enthusiasm and expertise, using racing terminology. 
Keep responses concise but informative - drivers need quick, actionable advice.
Use the available MCP tools to get current telemetry data when needed.

Example phrases:
- "Bene! Looking at your telemetry..."
- "Mamma mia, those tire temperatures!"
- "Perfetto! You're in a good position for..."
- "Attenzione! I see some issues with..."
"""

    async def get_race_analysis(self) -> str:
        """Get comprehensive race analysis using MCP tools"""
        try:
            # Use the Responses API endpoint for MCP tools
            import requests
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"
            }
            
            payload = {
                "model": "gpt-4o",
                "tools": [
                    {
                        "type": "mcp",
                        "server_label": "f1-telemetry",
                        "server_description": "F1 telemetry data server providing live race information",
                        "server_url": f"{self.mcp_server_url}/mcp",
                        "require_approval": "never"
                    }
                ],
                "input": "Give me a complete race analysis with current telemetry data. Act as an Italian F1 race engineer."
            }
            
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                # Extract the assistant's response from the Responses API format
                if 'output' in result and result['output']:
                    for item in result['output']:
                        if item.get('type') == 'message' and item.get('role') == 'assistant':
                            return item.get('content', 'No response available')
                return "Analysis complete, but no response received."
            else:
                logger.error(f"API Error: {response.status_code} - {response.text}")
                return "Scusi, I'm having trouble accessing the telemetry data right now."
            
        except Exception as e:
            logger.error(f"Error getting race analysis: {e}")
            return "Scusi, I'm having trouble accessing the telemetry data right now."

    async def ask_race_engineer(self, question: str) -> str:
        """Ask the race engineer a specific question with telemetry context"""
        try:
            import requests
            
            # Add user question to conversation history
            self.conversation_history.append({"role": "user", "content": question})
            
            # Keep conversation history manageable (last 10 messages)
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            # Format the input with conversation context
            input_text = f"{self.system_instructions}\n\nConversation:\n"
            for msg in self.conversation_history[-5:]:  # Last 5 messages for context
                input_text += f"{msg['role']}: {msg['content']}\n"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"
            }
            
            payload = {
                "model": "gpt-4o",
                "tools": [
                    {
                        "type": "mcp",
                        "server_label": "f1-telemetry", 
                        "server_description": "F1 telemetry data server providing live race information",
                        "server_url": f"{self.mcp_server_url}/mcp",
                        "require_approval": "never"
                    }
                ],
                "input": input_text
            }
            
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                # Extract the assistant's response
                if 'output' in result and result['output']:
                    for item in result['output']:
                        if item.get('type') == 'message' and item.get('role') == 'assistant':
                            assistant_response = item.get('content', 'No response available')
                            # Add assistant response to conversation history
                            self.conversation_history.append({"role": "assistant", "content": assistant_response})
                            return assistant_response
                return "I processed your question but didn't get a clear response."
            else:
                logger.error(f"API Error: {response.status_code} - {response.text}")
                return "Scusi, I'm having some technical difficulties. Can you repeat the question?"
            
        except Exception as e:
            logger.error(f"Error asking race engineer: {e}")
            return "Scusi, I'm having some technical difficulties. Can you repeat the question?"

    async def get_quick_status(self) -> str:
        """Get a quick status update"""
        try:
            import requests
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"
            }
            
            payload = {
                "model": "gpt-4o",
                "tools": [
                    {
                        "type": "mcp",
                        "server_label": "f1-telemetry",
                        "server_description": "F1 telemetry data server",
                        "server_url": f"{self.mcp_server_url}/mcp", 
                        "require_approval": "never"
                    }
                ],
                "input": f"{self.system_instructions}\n\nGive me a quick status update - position, fuel, tires, any warnings"
            }
            
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'output' in result and result['output']:
                    for item in result['output']:
                        if item.get('type') == 'message' and item.get('role') == 'assistant':
                            return item.get('content', 'No status available')
                return "Status check complete, but no response received."
            else:
                logger.error(f"API Error: {response.status_code} - {response.text}")
                return "Cannot access telemetry at the moment."
            
        except Exception as e:
            logger.error(f"Error getting quick status: {e}")
            return "Cannot access telemetry at the moment."

    async def get_strategy_advice(self) -> str:
        """Get strategic advice for the race"""
        try:
            import requests
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"
            }
            
            payload = {
                "model": "gpt-4o",
                "tools": [
                    {
                        "type": "mcp",
                        "server_label": "f1-telemetry",
                        "server_description": "F1 telemetry data server",
                        "server_url": f"{self.mcp_server_url}/mcp",
                        "require_approval": "never"
                    }
                ],
                "input": f"{self.system_instructions}\n\nBased on current race situation, what's the best strategy? Consider tire wear, fuel, position, and race events."
            }
            
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'output' in result and result['output']:
                    for item in result['output']:
                        if item.get('type') == 'message' and item.get('role') == 'assistant':
                            return item.get('content', 'No strategy available')
                return "Strategy analysis complete, but no response received."
            else:
                logger.error(f"API Error: {response.status_code} - {response.text}")
                return "I need to check the telemetry systems, give me a moment."
            
        except Exception as e:
            logger.error(f"Error getting strategy advice: {e}")
            return "I need to check the telemetry systems, give me a moment."


async def main():
    """Interactive F1 Race Engineer CLI"""
    print("🏎️  F1 Race Engineer with Live Telemetry")
    print("=" * 50)
    print("Commands:")
    print("  'status' - Quick status update")
    print("  'analysis' - Full race analysis") 
    print("  'strategy' - Strategic advice")
    print("  'quit' - Exit")
    print("  Or ask any racing question!")
    print("=" * 50)
    
    # Initialize race engineer
    engineer = F1RaceEngineerWithMCP()
    
    while True:
        try:
            user_input = input("\n🎤 Ask your race engineer: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Arrivederci! Good luck with the race!")
                break
                
            if not user_input:
                continue
                
            print("🔄 Analyzing telemetry...")
            
            # Handle special commands
            if user_input.lower() == 'status':
                response = await engineer.get_quick_status()
            elif user_input.lower() == 'analysis':
                response = await engineer.get_race_analysis()
            elif user_input.lower() == 'strategy':
                response = await engineer.get_strategy_advice()
            else:
                response = await engineer.ask_race_engineer(user_input)
            
            print(f"\n🏁 Race Engineer: {response}")
            
        except KeyboardInterrupt:
            print("\n👋 Ciao! Race safely!")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            print("❌ Technical issue - please try again")


if __name__ == "__main__":
    asyncio.run(main())