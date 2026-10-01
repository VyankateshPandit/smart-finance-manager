from typing import List, Optional
from pydantic import BaseModel, Field

class ActionableTip(BaseModel):
    title: str = Field(
        description="Short, impactful title for the recommendation (e.g., 'Trim Dining Out', 'Automate Emergency Fund')"
    )
    category: str = Field(
        description="Relevant expense category: Food, Travel, Entertainment, Shopping, Other, or Savings"
    )
    estimated_monthly_savings: Optional[str] = Field(
        default=None,
        description="Estimated monthly savings potential (e.g. '₹1,500 - ₹2,500')"
    )
    advice: str = Field(
        description="Clear, practical step-by-step guidance on how to implement this recommendation"
    )


class FinancialAdviceResponse(BaseModel):
    summary: str = Field(
        description="Executive 1-2 sentence takeaway summarizing the user's financial standing and primary next step"
    )
    risk_level: str = Field(
        description="Overall spending risk level: 'Low', 'Moderate', or 'High'"
    )
    spending_assessment: str = Field(
        description="Brief analysis of current spending habits and category ratios"
    )
    actionable_tips: List[ActionableTip] = Field(
        default_factory=list,
        description="2 to 4 concrete, prioritized recommendations"
    )
    key_takeaways: List[str] = Field(
        default_factory=list,
        description="Quick bullet points summarizing main insights"
    )

    def to_formatted_markdown(self) -> str:
        """Converts structured response to human-readable formatted Markdown."""
        lines = []
        lines.append(f"### Financial Summary ({self.risk_level} Risk)")
        lines.append(f"{self.summary}\n")
        lines.append(f"**Assessment:** {self.spending_assessment}\n")

        if self.actionable_tips:
            lines.append("#### Recommended Action Steps:")
            for idx, tip in enumerate(self.actionable_tips, 1):
                savings = f" *(Potential Savings: {tip.estimated_monthly_savings})*" if tip.estimated_monthly_savings else ""
                lines.append(f"{idx}. **{tip.title}** [{tip.category}]{savings}")
                lines.append(f"   {tip.advice}\n")

        if self.key_takeaways:
            lines.append("#### Key Takeaways:")
            for item in self.key_takeaways:
                lines.append(f"• {item}")

        return "\n".join(lines)
