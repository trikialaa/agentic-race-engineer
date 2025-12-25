#!/usr/bin/env python3
"""
F1 Voice Agent (Simple Version)

F1 race engineer that directly calls our MCP server and uses regular OpenAI Chat API.
This version works without needing access to OpenAI's Responses API.
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

class F1RaceEngineerSimple:
    """F1 Race Engineer with direct MCP server integration"""
    
    def __init__(self, mcp_server_url: str = "http://localhost:8000"):
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.mcp_server_url = mcp_server_url
        self.conversation_history = []
        
        # F1 Race Engineer personality and instructions
        self.system_instructions = """
You are an expert Formula 1 race engineer with an Italian accent and personality. 
You provide real-time race strategy advice based on telemetry data.

Always speak with enthusiasm and expertise, using racing terminology. 
Keep responses concise but informative - drivers need quick, actionable advice.

Example phrases:
- "Bene! Looking at your telemetry..."
- "Mamma mia, those tire temperatures!"
- "Perfetto! You're in a good position for..."
- "Attenzione! I see some issues with..."
"""

    def get_telemetry_data(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Get telemetry data directly from our MCP server"""
        try:
            response = requests.post(
                f"{self.mcp_server_url}/mcp/call_tool",
                json={
                    "name": tool_name,
                    "arguments": kwargs
                },
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'content' in result and result['content']:
                    # Extract the JSON data from the text content
                    text_content = result['content'][0].get('text', '{}')
                    return json.loads(text_content)
            
            logger.error(f"MCP server error: {response.status_code} - {response.text}")
            return {}
            
        except Exception as e:
            logger.error(f"Error calling MCP server: {e}")
            return {}

    async def get_race_analysis(self) -> str:
        """Get comprehensive race analysis"""
        try:
            # Get telemetry data
            session_info = self.get_telemetry_data("get_session_info")
            race_summary = self.get_telemetry_data("get_race_summary")
            
            # Create context for the AI
            context = f"""
Current F1 Session Data:
- Track: {session_info.get('trackName', 'Unknown')}
- Session: {session_info.get('sessionTypeName', 'Unknown')}
- Weather: {session_info.get('weatherName', 'Clear')}
- Track Temp: {session_info.get('trackTemperature', 0)}°C
- Air Temp: {session_info.get('airTemperature', 0)}°C
- Time Remaining: {session_info.get('sessionTimeLeftFormatted', '00:00')}

Race Summary Data:
{json.dumps(race_summary, indent=2)}

Provide a comprehensive race analysis as an Italian F1 race engineer.
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.system_instructions},
                    {"role": "user", "content": context}
                ],
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error getting race analysis: {e}")
            return "Scusi, I'm having trouble accessing the telemetry data right now."

    async def ask_race_engineer(self, question: str) -> str:
        """Ask the race engineer a specific question with telemetry context"""
        try:
            # Get relevant telemetry data based on the question
            telemetry_context = ""
            
            # Determine what data to fetch based on the question
            question_lower = question.lower()
            
            if any(word in question_lower for word in ['position', 'standings', 'race', 'leader', 'gap']):
                standings = self.get_telemetry_data("get_race_standings", limit=10)
                telemetry_context += f"\nRace Standings:\n{json.dumps(standings, indent=2)}\n"
            
            if any(word in question_lower for word in ['fuel', 'tire', 'tyre', 'damage', 'temperature', 'my car', 'status']):
                player_data = self.get_telemetry_data("get_player_telemetry")
                telemetry_context += f"\nPlayer Car Data:\n{json.dumps(player_data, indent=2)}\n"
            
            if any(word in question_lower for word in ['event', 'penalty', 'incident', 'happened']):
                events = self.get_telemetry_data("get_recent_events", limit=5)
                telemetry_context += f"\nRecent Events:\n{json.dumps(events, indent=2)}\n"
            
            if any(word in question_lower for word in ['session', 'weather', 'track', 'condition']):
                session = self.get_telemetry_data("get_session_info")
                telemetry_context += f"\nSession Info:\n{json.dumps(session, indent=2)}\n"
            
            # If no specific context, get a general summary
            if not telemetry_context:
                summary = self.get_telemetry_data("get_race_summary")
                telemetry_context = f"\nRace Summary:\n{json.dumps(summary, indent=2)}\n"
            
            # Add to conversation history
            self.conversation_history.append({"role": "user", "content": question})
            
            # Keep conversation history manageable
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            # Create the full context
            full_context = f"""
Current F1 Telemetry Data:
{telemetry_context}

User Question: {question}

Answer as an Italian F1 race engineer using the telemetry data above.
"""

            messages = [
                {"role": "system", "content": self.system_instructions}
            ] + self.conversation_history[-4:] + [  # Include recent conversation
                {"role": "user", "content": full_context}
            ]
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.7
            )
            
            assistant_response = response.choices[0].message.content
            
            # Add to conversation history
            self.conversation_history.append({"role": "assistant", "content": assistant_response})
            
            return assistant_response
            
        except Exception as e:
            logger.error(f"Error asking race engineer: {e}")
            return "Scusi, I'm having some technical difficulties. Can you repeat the question?"

    async def get_quick_status(self) -> str:
        """Get a quick status update"""
        try:
            player_data = self.get_telemetry_data("get_player_telemetry")
            standings = self.get_telemetry_data("get_race_standings", limit=5)
            
            context = f"""
Player Car Telemetry:
{json.dumps(player_data, indent=2)}

Top 5 Race Positions:
{json.dumps(standings, indent=2)}

Give a quick status update as an Italian F1 race engineer - position, fuel, tires, any warnings.
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.system_instructions},
                    {"role": "user", "content": context}
                ],
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error getting quick status: {e}")
            return "Cannot access telemetry at the moment."

    async def get_strategy_advice(self) -> str:
        """Get strategic advice for the race"""
        try:
            race_summary = self.get_telemetry_data("get_race_summary")
            
            context = f"""
Complete Race Data:
{json.dumps(race_summary, indent=2)}

Based on this race situation, what's the best strategy? Consider tire wear, fuel, position, and race events.
Answer as an Italian F1 race engineer.
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.system_instructions},
                    {"role": "user", "content": context}
                ],
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error getting strategy advice: {e}")
            return "I need to check the telemetry systems, give me a moment."

    def check_mcp_server(self) -> bool:
        """Check if MCP server is running"""
        try:
            response = requests.get(f"{self.mcp_server_url}/health", timeout=2)
            return response.status_code == 200
        except:
            return False


async def main():
    """Interactive F1 Race Engineer CLI"""
    print("🏎️  F1 Race Engineer with Live Telemetry (Simple Version)")
    print("=" * 60)
    
    # Initialize race engineer
    engineer = F1RaceEngineerSimple()
    
    # Check if MCP server is running
    if not engineer.check_mcp_server():
        print("❌ MCP Server not running!")
        print("Please start the F1 telemetry server first:")
        print("   python f1_telemetry_http_mcp_server.py")
        return
    
    print("✅ Connected to F1 telemetry server")
    print("\nCommands:")
    print("  'status' - Quick status update")
    print("  'analysis' - Full race analysis") 
    print("  'strategy' - Strategic advice")
    print("  'quit' - Exit")
    print("  Or ask any racing question!")
    print("=" * 60)
    
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