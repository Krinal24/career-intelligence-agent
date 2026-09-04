from pydantic import BaseModel


class Experience(BaseModel):
    company: str
    role: str
    duration: str
    responsibilities: list[str]
    technologies: list[str]


class CareerProfile(BaseModel):
    name: str
    summary: str
    skills: list[str]
    experience: list[Experience]
    projects: list[str]
    certifications: list[str]