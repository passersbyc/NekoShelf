from abc import ABC, abstractmethod

class DownloadPlugin(ABC):
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this plugin can handle the given URL."""
        pass

    @abstractmethod
    def download(self, url: str, output_dir: str, **kwargs) -> tuple[bool, str, str]:
        """
        Download content from the URL.
        :param url: The URL to download from.
        :param output_dir: The directory to save the downloaded content.
        :param kwargs: Additional arguments (e.g., series_name).
        :return: (success, message, saved_path)
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the plugin."""
        pass
