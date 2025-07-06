import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
from host_config import get_host_display_name, get_primary_hosts

CONFIG_DIR = "config"
os.makedirs(CONFIG_DIR, exist_ok=True)

# Template constants
DEFAULT_TEMPLATES = {
    "anime": (
        "🎌 {romaji_title}" + (" ({english_title})" if "{english_title}" else "") + "\n\n"
        "⭐ Rating: {rating}/100\n"
        "📺 Episodes: {episodes}\n"
        "🎬 Studio: {studio}\n"
        "📅 Season: {season} {year}\n\n"
        "{overview}\n\n"
        "{thumbnail}\n\n"
        "📥 Downloads:\n"
        "{host1_name}: {host1_link}\n"
        "{host2_name}: {host2_link}\n\n"
        "🔗 Mirrors:\n{host_links}"
        ),
    "movie": (
        "🎬 {title} ({year})\n\n"
        "⭐ TMDb Rating: {rating}\n\n"
        "{overview}\n\n"
        "{thumbnail}\n\n"
        "📥 Premium Downloads:\n"
        "{host1_name}: {host1_link}\n"
        "{host2_name}: {host2_link}\n\n"
        "📥 Mirror Links:\n{host_links}"
    ),
    "tv_episode": (
        "📺 {full_title}\n\n"
        "🖥 Quality: {quality}\n\n"
        "{overview}\n\n"
        "{thumbnail}\n\n"
        "📥 Premium Downloads:\n"
        "{host1_name}: {host1_link}\n"
        "{host2_name}: {host2_link}\n\n"
        "📥 Mirror Links:\n{host_links}"
    ),
    "tv_season": (
        "📀 Complete Season {season}\n\n"
        "{overview}\n\n"
        "{thumbnail}\n\n"
        "📥 Premium Downloads:\n"
        "{host1_name}: {host1_link}\n"
        "{host2_name}: {host2_link}\n\n"
        "📥 Mirror Links:\n{host_links}"
    ),
    "default": "{title}\n\n{overview}\n\n{thumbnail}\n\n{host_links}"
    
}

SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "wp_url": "https://your-site.com",
    "wp_user": "admin",
    "wp_app_password": "your_password",
    "tmdb_api_key": "your_tmdb_key",
    "omdb_api_key": "",
    "preferred_image": "poster",
    "post_status": "publish",
    "include_thumbnails": True,
    "categories": ["Movies"],
    "tags": ["HD"],
    "skip_tmdb_if_unrecognized": True,
    "enable_omdb_fallback": False,  # Disabled by default
    "require_both_hosts": True,
    "title_mode": "clean",
    "thumbnail_folder": "",
    "enable_auto_update": True,
    "allow_post_deletion": False,
    "season_post_mode": "episode",
    "additional_hosts": [],
    "link_merge_behavior": "append",
    "debug_templates": False,
    "enable_anilist": True,
    "strict_resolution_matching": True,
    "preferred_anime_source": "anilist"  # or "tmdb"
}

class SettingsEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AutoUploader Settings")
        self.geometry("800x600")
        self.resizable(True, True)
        
        self.style = ttk.Style()
        self.style.configure('TFrame', background='#f0f0f0')
        self.style.configure('TLabel', background='#f0f0f0')
        
        self.settings = DEFAULT_SETTINGS.copy()
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                self.settings.update(json.load(f))

        # Initialize templates
        if "post_templates" not in self.settings:
            self.settings["post_templates"] = DEFAULT_TEMPLATES.copy()
        elif isinstance(self.settings.get("post_template"), str):  # Legacy support
            self.settings["post_templates"] = {
                "default": self.settings["post_template"],
                **DEFAULT_TEMPLATES
            }

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Create all tabs
        self.create_wordpress_tab(notebook)
        self.create_api_tab(notebook)
        self.create_post_tab(notebook)
        self.create_template_tab(notebook)
        self.create_host_config_tab(notebook)  # Add this line

        ttk.Button(main_frame, text="Save Settings", command=self.save).pack(side=tk.RIGHT)

    def create_wordpress_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="WordPress")

        wp_frame = ttk.LabelFrame(tab, text="WordPress Settings", padding=10)
        wp_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # URL
        ttk.Label(wp_frame, text="WordPress URL:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.wp_url = ttk.Entry(wp_frame, width=60)
        self.wp_url.insert(0, self.settings["wp_url"])
        self.wp_url.grid(row=0, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))

        # Username
        ttk.Label(wp_frame, text="Username:").grid(row=1, column=0, sticky="w", pady=(0, 5))
        self.wp_user = ttk.Entry(wp_frame, width=60)
        self.wp_user.insert(0, self.settings["wp_user"])
        self.wp_user.grid(row=1, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))

        # App Password
        ttk.Label(wp_frame, text="App Password:").grid(row=2, column=0, sticky="w", pady=(0, 5))
        self.wp_pass = ttk.Entry(wp_frame, show="*", width=60)
        self.wp_pass.insert(0, self.settings["wp_app_password"])
        self.wp_pass.grid(row=2, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))

    def create_api_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="API Settings")

        api_frame = ttk.LabelFrame(tab, text="API Configuration", padding=10)
        api_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # TMDb API Key
        ttk.Label(api_frame, text="TMDb API Key:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.tmdb = ttk.Entry(api_frame, width=60)
        self.tmdb.insert(0, self.settings["tmdb_api_key"])
        self.tmdb.grid(row=0, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))

        # OMDb API Key
        ttk.Label(api_frame, text="OMDb API Key:").grid(row=1, column=0, sticky="w", pady=(0, 5))
        self.omdb = ttk.Entry(api_frame, width=60)
        self.omdb.insert(0, self.settings.get("omdb_api_key", ""))
        self.omdb.grid(row=1, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))
        
        self.enable_anilist = tk.BooleanVar(value=self.settings.get("enable_anilist", True))
        ttk.Checkbutton(api_frame, text="Enable AniList for anime detection", variable=self.enable_anilist).grid(row=5, column=1, sticky="w", pady=(0, 5))

        self.anime_source = ttk.Combobox(api_frame, values=["anilist", "tmdb"], width=57)
        self.anime_source.set(self.settings.get("preferred_anime_source", "anilist"))
        self.anime_source.grid(row=6, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))
        ttk.Label(api_frame, text="Preferred anime source:").grid(row=6, column=0, sticky="w", pady=(0, 5))

        # Checkboxes
        self.enable_omdb = tk.BooleanVar(value=self.settings.get("enable_omdb_fallback", False))
        ttk.Checkbutton(api_frame, text="Enable OMDb fallback", variable=self.enable_omdb).grid(row=2, column=1, sticky="w", pady=(0, 5))

        self.skip_tmdb = tk.BooleanVar(value=self.settings["skip_tmdb_if_unrecognized"])
        ttk.Checkbutton(api_frame, text="Skip TMDb if filename is unrecognized", variable=self.skip_tmdb).grid(row=3, column=1, sticky="w", pady=(0, 5))

        self.require_both = tk.BooleanVar(value=self.settings.get("require_both_hosts", True))
        ttk.Checkbutton(api_frame, text="Require both Rapidgator and Nitroflare links", variable=self.require_both).grid(row=4, column=1, sticky="w", pady=(0, 5))

    def create_post_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Post Settings")

        post_frame = ttk.LabelFrame(tab, text="Post Configuration", padding=10)
        post_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Preferred Image
        ttk.Label(post_frame, text="Preferred Image:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.img_choice = ttk.Combobox(post_frame, values=["poster", "backdrop"], width=57)
        self.img_choice.set(self.settings["preferred_image"])
        self.img_choice.grid(row=0, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))

        # Post Status
        ttk.Label(post_frame, text="Post Status:").grid(row=1, column=0, sticky="w", pady=(0, 5))
        self.post_status = ttk.Combobox(post_frame, values=["publish", "draft"], width=57)
        self.post_status.set(self.settings["post_status"])
        self.post_status.grid(row=1, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))

        # Title Mode
        ttk.Label(post_frame, text="Title Mode:").grid(row=2, column=0, sticky="w", pady=(0, 5))
        self.title_mode = ttk.Combobox(post_frame, values=["original", "clean"], width=57)
        self.title_mode.set(self.settings["title_mode"])
        self.title_mode.grid(row=2, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))

        # Thumbnail Path
        ttk.Label(post_frame, text="Thumbnail Folder:").grid(row=3, column=0, sticky="w", pady=(0, 5))
        thumb_frame = ttk.Frame(post_frame)
        thumb_frame.grid(row=3, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))
        self.thumb_path = ttk.Entry(thumb_frame, width=50)
        self.thumb_path.insert(0, self.settings.get("thumbnail_folder", ""))
        self.thumb_path.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(thumb_frame, text="Browse", command=self.browse_thumb_path).pack(side=tk.LEFT, padx=5)

        # Include Thumbnails
        self.include_thumbs = tk.BooleanVar(value=self.settings["include_thumbnails"])
        ttk.Checkbutton(post_frame, text="Include thumbnails in body", variable=self.include_thumbs).grid(row=4, column=1, sticky="w", pady=(0, 5))

        # Categories
        ttk.Label(post_frame, text="Categories (comma-separated):").grid(row=5, column=0, sticky="w", pady=(0, 5))
        self.categories = ttk.Entry(post_frame, width=60)
        self.categories.insert(0, ",".join(self.settings["categories"]))
        self.categories.grid(row=5, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))

        # Tags
        ttk.Label(post_frame, text="Tags (comma-separated):").grid(row=6, column=0, sticky="w", pady=(0, 5))
        self.tags = ttk.Entry(post_frame, width=60)
        self.tags.insert(0, ",".join(self.settings["tags"]))
        self.tags.grid(row=6, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))
        
        # Posting Mode
        ttk.Label(post_frame, text="Posting Mode:").grid(row=7, column=0, sticky="w", pady=(0, 5))
        self.post_mode = ttk.Combobox(post_frame, values=["episode", "season"], width=57)
        self.post_mode.set(self.settings.get("season_post_mode", "episode"))
        self.post_mode.grid(row=7, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))
        
        # Auto Update
        self.auto_update = tk.BooleanVar(value=self.settings.get("enable_auto_update", True))
        ttk.Checkbutton(post_frame, text="Enable automatic post updates", variable=self.auto_update).grid(
            row=8, column=1, sticky="w", pady=(0, 5))
        
        # Allow Deletion
        self.allow_delete = tk.BooleanVar(value=self.settings.get("allow_post_deletion", False))
        ttk.Checkbutton(post_frame, text="Allow post deletion", variable=self.allow_delete).grid(
            row=9, column=1, sticky="w", pady=(0, 5))
        
        # Additional Hosts
        ttk.Label(post_frame, text="Additional Hosts (comma-separated):").grid(
            row=10, column=0, sticky="w", pady=(0, 5))
        self.additional_hosts = ttk.Entry(post_frame, width=60)
        self.additional_hosts.insert(0, ",".join(self.settings.get("additional_hosts", [])))
        self.additional_hosts.grid(row=10, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))
        
        # Strict Resolution Matching
        self.strict_res = tk.BooleanVar(value=self.settings.get("strict_resolution_matching", True))
        ttk.Checkbutton(post_frame, text="Require exact resolution matches", variable=self.strict_res).grid(
            row=11, column=1, sticky="w", pady=(0, 5))

    def browse_thumb_path(self):
        path = filedialog.askdirectory()
        if path:
            self.thumb_path.delete(0, "end")
            self.thumb_path.insert(0, path)

    def create_template_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Templates")
        
        ttk.Label(tab, text="Template Type:").pack(anchor="w")
        # Add "anime" to the values list
        self.template_type = ttk.Combobox(tab, values=["movie", "tv_episode", "tv_season", "anime", "default"])
        self.template_type.pack(fill=tk.X, pady=(0, 10))
        self.template_type.set("default")
        self.template_type.bind("<<ComboboxSelected>>", self.load_template)
        
        self.template_editor = tk.Text(tab, height=15, wrap=tk.WORD)
        self.template_editor.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(tab, 
             text="Available placeholders: {title}, {year}, {season}, {episode}, {episodes}, "
                  "{season_year}, {rating}, {overview}, {thumbnail}, {host_links}, "
                  "{rapidgator_link}, {nitroflare_link}, {quality}",
             foreground="gray").pack(anchor="w")
        
        self.load_template()

    def load_template(self, event=None):
        """Load selected template into editor"""
        template_type = self.template_type.get()
        current_content = self.settings["post_templates"].get(
            template_type, 
            DEFAULT_TEMPLATES.get(template_type, "")
        )
        
        # Get primary hosts from settings or use defaults
        primary_hosts = self.settings.get("primary_hosts", ["rapidgator", "nitroflare"])
        
        # Replace host placeholders if they exist in the template
        if "{host1_name}" in current_content and len(primary_hosts) > 0:
            current_content = current_content.replace(
                "{host1_name}", get_host_display_name(primary_hosts[0])
            ).replace(
                "{host1_link}", f"{{{primary_hosts[0]}_link}}"
            )
        
        if "{host2_name}" in current_content and len(primary_hosts) > 1:
            current_content = current_content.replace(
                "{host2_name}", get_host_display_name(primary_hosts[1])
            ).replace(
                "{host2_link}", f"{{{primary_hosts[1]}_link}}"
            )
        
        self.template_editor.delete("1.0", "end")
        self.template_editor.insert("1.0", current_content)

    def save_templates(self):
        """Save all templates back to settings"""
        if hasattr(self, 'template_type'):
            template_type = self.template_type.get()
            new_content = self.template_editor.get("1.0", "end").strip()
            
            if new_content != DEFAULT_TEMPLATES.get(template_type, ""):
                self.settings["post_templates"][template_type] = new_content
            elif template_type in self.settings["post_templates"]:
                del self.settings["post_templates"][template_type]
                
    def create_host_config_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Hosts")
        
        host_frame = ttk.LabelFrame(tab, text="Host Configuration", padding=10)
        host_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Primary hosts
        ttk.Label(host_frame, text="Primary Hosts (comma-separated):").grid(
            row=0, column=0, sticky="w", pady=(0, 5))
        self.primary_hosts = ttk.Entry(host_frame, width=60)
        self.primary_hosts.insert(0, ",".join(self.settings.get("primary_hosts", ["rapidgator", "nitroflare"])))
        self.primary_hosts.grid(row=0, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))
        
        # Mirror hosts
        ttk.Label(host_frame, text="Mirror Hosts (comma-separated):").grid(
            row=1, column=0, sticky="w", pady=(0, 5))
        self.mirror_hosts = ttk.Entry(host_frame, width=60)
        self.mirror_hosts.insert(0, ",".join(self.settings.get("mirror_hosts", [])))
        self.mirror_hosts.grid(row=1, column=1, sticky="ew", pady=(0, 5), padx=(5, 0))
    
    def save(self):
        """Save all settings to file"""
        # Save all regular settings first
        self.settings["wp_url"] = self.wp_url.get().strip()
        self.settings["wp_user"] = self.wp_user.get().strip()
        self.settings["wp_app_password"] = self.wp_pass.get().strip()
        self.settings["tmdb_api_key"] = self.tmdb.get().strip()
        self.settings["omdb_api_key"] = self.omdb.get().strip()
        self.settings["enable_omdb_fallback"] = self.enable_omdb.get()
        self.settings["preferred_image"] = self.img_choice.get()
        self.settings["post_status"] = self.post_status.get()
        self.settings["include_thumbnails"] = self.include_thumbs.get()
        self.settings["skip_tmdb_if_unrecognized"] = self.skip_tmdb.get()
        self.settings["require_both_hosts"] = self.require_both.get()
        self.settings["title_mode"] = self.title_mode.get()
        self.settings["categories"] = [c.strip() for c in self.categories.get().split(",") if c.strip()]
        self.settings["tags"] = [t.strip() for t in self.tags.get().split(",") if t.strip()]
        self.settings["thumbnail_folder"] = self.thumb_path.get().strip()
        self.settings["enable_auto_update"] = self.auto_update.get()
        self.settings["allow_post_deletion"] = self.allow_delete.get()
        self.settings["season_post_mode"] = self.post_mode.get()
        self.settings["additional_hosts"] = [h.strip() for h in self.additional_hosts.get().split(",") if h.strip()]

        # Save host configurations
        self.settings["primary_hosts"] = [
            h.strip() for h in self.primary_hosts.get().split(",") 
            if h.strip()
        ]
        self.settings["mirror_hosts"] = [
            h.strip() for h in self.mirror_hosts.get().split(",") 
            if h.strip()
        ]

        self.save_templates()
        
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2)
        
        messagebox.showinfo("Saved", "Settings saved successfully.")
        self.destroy()

if __name__ == "__main__":
    app = SettingsEditor()
    app.mainloop()