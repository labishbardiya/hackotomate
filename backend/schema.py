from pydantic import BaseModel, Field
from typing import List, Optional

class HackathonDetails(BaseModel):
    name: str = Field(description="The formal name of the hackathon event.")
    organizer: str = Field(description="The platform, university, or company hosting the event.")
    description_summary: str = Field(description="A concise summary (1-2 sentences) of what the hackathon is about, its themes, and focus.")
    start_date: str = Field(description="The start date of the event in YYYY-MM-DD format. If only month/year is available, guess best fit.")
    end_date: str = Field(description="The closing date of the event in YYYY-MM-DD format.")
    registration_deadline: Optional[str] = Field(None, description="The last date to register/apply for the hackathon in YYYY-MM-DD format.")
    prize_pool: str = Field(description="Total prize cash or a quick description of rewards (e.g., '$50,000 USD', 'MacBooks & Grants').")
    tags: List[str] = Field(description="A list of 3-5 keywords representing categories or tracks (e.g., ['AI/ML', 'Web3', 'Healthcare']).")
    registration_url: str = Field(description="The exact direct registration or landing URL found on the page.")

class TaxonomyDecision(BaseModel):
    is_new_track_required: bool = Field(description="True if the event details do not fit cleanly into existing track boundaries.")
    matched_track_slug: str = Field(description="If fitting an existing track, output its exact slug. Otherwise output 'NONE'.")
    suggested_new_track_name: str = Field(description="If a new track is required, provide a punchy 2-3 word title (e.g. 'BioTech AI').")
    suggested_new_track_slug: str = Field(description="URL safe lowercase hyphenated slug version of the suggested new track name.")
    suggested_new_track_summary: str = Field(description="If a new track is required, provide a brief 1-sentence description of the track category.")
