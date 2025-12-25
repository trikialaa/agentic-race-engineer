import asyncio
from fastmcp import Client

async def main():
	client = Client("http://127.0.0.1:20915/mcp")
	
	async with client:
		tools = await client.list_tools()
		for tool in tools:
			print(tool.name)
			try:
				result = await client.call_tool(tool.name, {})
				print(result)
			except Exception as e:
				print('Error calling tool:', e)
			print("\n" * 2)


asyncio.run(main())