import json
from typing import Dict, Any

from langsmith import traceable

def process_bing_search_results(data: Dict[str, Any]) -> Dict[str, Any]:
    processed_data = {
        "answer": None,  # Bing doesn't provide a direct answer like Tavily
        "follow_up_questions": None,  # Bing has related searches but keeping format consistent
        "images": [],
        "query": data["queryContext"]["originalQuery"],
        "response_time": None,  # Bing doesn't provide this
        "results": []
    }
    
    # Process web results
    if "webPages" in data and "value" in data["webPages"]:
        for result in data["webPages"]["value"]:
            processed_result = {
                "content": result["snippet"],
                "raw_content": result.get("snippet", ""),  # Using snippet as raw_content
                "score": 0.0,  # Bing doesn't provide a comparable score
                "title": result["name"],
                "url": result["url"]
            }
            processed_data["results"].append(processed_result)
    
    # Process images if available
    if "images" in data and "value" in data["images"]:
        for image in data["images"]["value"][:10]:
            processed_image = {
                "url": image["contentUrl"],
                "thumbnail_url": image.get("thumbnailUrl", ""),
                "title": image.get("name", "")
            }
            processed_data["images"].append(processed_image)
    
    return processed_data

from typing import Dict, Any, Optional, List
import os
import requests

class BingSearchClient:
    ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"
    
    def __init__(self):
        self.api_key = os.getenv("BING_API_KEY")
        if not self.api_key:
            raise ValueError("Bing API key is not set. Please provide it or set BING_API_KEY environment variable.")
        
        self.headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Accept": "application/json",
        }
        
    def search(self, query: str, max_results: int = 10, sites: List[str] = None, freshness: str = None, **kwargs) -> Dict[str, Any]:
        params = {
            "q": query,
            "count": max_results,
            "offset": kwargs.get("offset", 0),
            "safeSearch": kwargs.get("safe_search", "Moderate"),
        }

        # Add freshness if provided
        if freshness:
            params["freshness"] = freshness

        if sites:
            site_query = " OR ".join(f"site:{site}" for site in sites)
            params["q"] += f" {site_query}"
        
        try:
            response = requests.get(self.ENDPOINT, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error occurred: {e}")
            return {"error": str(e)}
        except requests.exceptions.RequestException as e:
            print(f"An error occurred while requesting: {e}")
            return {"error": str(e)}

@traceable
def deduplicate_and_format_sources(search_response, max_tokens_per_source=1000, include_raw_content=True):
    """
    Format and deduplicate search results from response.
    
    Args:
        search_response (dict): Response containing search results
        max_tokens_per_source (int): Max tokens per source snippet
        include_raw_content (bool): Whether to include full content
        
    Returns:
        str: Formatted string with deduplicated sources
    """
    if isinstance(search_response, str):
        search_response = json.loads(search_response)
    
    if not isinstance(search_response, dict):
        raise ValueError("Input must be a dictionary")

    # Extract sources list
    if 'results' in search_response:
        sources_list = search_response['results']
    elif 'top_web_results' in search_response:
        sources_list = search_response['top_web_results']
    else:
        raise ValueError("Missing results in search response")

    # Deduplicate by URL
    unique_sources = {}
    for source in sources_list:
        url = source.get('url')
        if url and url not in unique_sources:
            unique_sources[url] = source

    # Format output
    formatted_text = "Sources:\n\n"
    for source in unique_sources.values():
        title = source.get('title', 'No Title')
        content = source.get('content', source.get('snippet', '[No content]'))
        url = source.get('url', '[No URL]')

        # Truncate content if needed
        if not include_raw_content and len(content) > max_tokens_per_source:
            content = content[:max_tokens_per_source] + "..."

        formatted_text += f"Title: {title}\n"
        formatted_text += f"URL: {url}\n"
        formatted_text += f"Content: {content}\n\n"

    return formatted_text


def format_sources(search_results):
    """Format search results into a bullet-point list of sources."""
    try:
        # Handle string input
        if isinstance(search_results, str):
            search_results = json.loads(search_results)
            
        # Handle dict input
        if not isinstance(search_results, dict):
            raise ValueError("Input must be a dictionary or JSON string")
            
        # Extract results safely
        results = search_results.get('results', [])
        if not results:
            return "No results found"
            
        # Format sources
        formatted_sources = []
        for source in results:
            title = source.get('title', 'No Title')
            url = source.get('url', 'No URL')
            formatted_sources.append(f"* {title} : {url}")
            
        return '\n'.join(formatted_sources)
        
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON string input")
    except Exception as e:
        return f"Error formatting sources: {str(e)}"

@traceable
def bing_search(query,max_results=3, sites=[],include_raw_content=True):
    """ Search the web using Bing engine.
    
    Args:
        query (str): The search query to execute
        include_raw_content (bool): Whether to include the raw_content from Tavily in the formatted string
        max_results (int): Maximum number of results to return
        
    Returns:
        dict: Tavily search response containing:
            - results (list): List of search result dictionaries, each containing:
                - title (str): Title of the search result
                - url (str): URL of the search result
                - content (str): Snippet/summary of the content
                - raw_content (str): Full content of the page if available"""

    client = BingSearchClient()
    result = client.search(query, max_results=max_results, sites=sites)
    return json.dumps(process_bing_search_results(result), indent=2, ensure_ascii=False)