import matplotlib.pyplot as plt
import numpy as np
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
import os

def add_logo(ax, team_code, x, y, zoom=1.0):
    logo_path = f"docs/logos/{team_code}.png"
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).convert("RGBA")
            # Crop transparent margins so the logo fully fills the box
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
            
            # Use thumbnail to preserve aspect ratio (prevents squishing)
            img.thumbnail((70, 70), Image.Resampling.LANCZOS)
            
            imagebox = OffsetImage(img, zoom=zoom)
            ab = AnnotationBbox(imagebox, (x, y), frameon=False, xycoords='data', box_alignment=(0.5, 0.5))
            ax.add_artist(ab)
            return True
        except Exception as e:
            print(f"Error loading logo for {team_code}: {e}")
    return False

def plot_diverging_bar_chart_with_logos(
    title: str,
    subtitle: str,
    teams: list,
    values: list,
    context_texts: list,
    x_label: str,
    filename: str
):
    """
    Generates a premium diverging horizontal bar chart with team logos.
    """
    # Setup Figure (Increased height to 15 for better row spacing)
    fig, ax = plt.subplots(figsize=(14, 15))
    fig.patch.set_facecolor('#0B101E')
    ax.set_facecolor('#0B101E')
    
    # Colors: Green for positive, Red for negative, Gray for zero
    colors = []
    for v in values:
        if v > 0: colors.append('#00E676')
        elif v < 0: colors.append('#FF1744')
        else: colors.append('#9E9E9E')
        
    y_pos = np.arange(len(teams))
    
    # Plot Bars
    bars = ax.barh(y_pos, values, color=colors, height=0.6, alpha=0.9, edgecolor='white', linewidth=0.5)
    
    # Determine logo X position based on minimum value to align them in a column
    min_x = min(values) - 3 if values else -3
    
    # Add Logos and Text annotations
    for i, (bar, team, val, ctx) in enumerate(zip(bars, teams, values, context_texts)):
        # Clear default Y text
        ax.text(0, y_pos[i], "", va='center')
        
        # Add Logo
        add_logo(ax, team, min_x, y_pos[i], zoom=0.40)
        
        # Add Team Acronym
        ax.text(min_x + 1.2, y_pos[i], team, va='center', ha='left', color='white', fontsize=12, fontweight='bold', alpha=0.8)
        
        # Value Annotation on Bars
        text_x = val + 0.5 if val > 0 else (val - 0.5 if val < 0 else 0.5)
        ha = 'left' if val >= 0 else 'right'
        label = f"+{val}" if val > 0 else f"{val}"
        ax.text(text_x, y_pos[i], label, va='center', ha=ha, color='white', fontsize=14, fontweight='bold')
        
        # Context Text (e.g., Act: X | Pred: Y)
        ctx_x = -2 if val >= 0 else 2
        ctx_ha = 'right' if val >= 0 else 'left'
        if val == 0:
            ctx_x = -2
            ctx_ha = 'right'
            
        ax.text(ctx_x, y_pos[i], ctx, va='center', ha=ctx_ha, color='#B0BEC5', fontsize=10, style='italic')

    # Titles
    plt.suptitle(title, color='#FFD700', fontsize=28, fontweight='bold', fontname='Impact', y=0.96)
    ax.set_title(subtitle, color='white', fontsize=16, pad=20, alpha=0.9)
    
    # Grid and Axes
    ax.axvline(0, color='white', linewidth=2, linestyle='-')
    ax.xaxis.grid(True, color='#263238', linestyle='--', alpha=0.7)
    ax.set_axisbelow(True)
    
    # Limits
    ax.set_xlim(min_x - 1, max(values) + 3 if values else 3)
    ax.set_yticks([]) 
    
    # Styling borders
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color('#546E7A')
    ax.tick_params(axis='x', colors='white', labelsize=12)
    
    ax.set_xlabel(x_label, color='#B0BEC5', fontsize=12, labelpad=10)
    
    plt.tight_layout()
    plt.subplots_adjust(top=0.88, left=0.05, right=0.95)
    
    plt.savefig(filename, dpi=200, facecolor=fig.get_facecolor(), bbox_inches='tight')
    print(f"Chart saved to {filename}")
    
    # Close the figure to free memory
    plt.close(fig)


def ratings_path(base):
    """Path of this round's ratings file (e.g. 'wpa_ratings' -> 'wpa_ratings_R4.json').

    Returns None if the file does not exist, so callers skip instead of
    silently charting a previous season's unsuffixed file.
    """
    round_suffix = os.environ.get('EUROLEAGUE_ROUND_SUFFIX', '')
    path = f'{base}{round_suffix}.json'
    return path if os.path.exists(path) else None
