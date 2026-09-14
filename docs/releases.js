// Public API only. A useful Releases link remains when JavaScript or GitHub is unavailable.
(async () => {
  const status = document.getElementById('release-status');
  const link = document.getElementById('release-link');
  try {
    const response = await fetch('https://api.github.com/repos/kkaan/conesrs-releases/releases?per_page=20', {signal: AbortSignal.timeout(8000)});
    if (!response.ok) throw new Error('Release lookup unavailable');
    const releases = await response.json();
    const candidates = releases.filter(r => !r.draft);
    const release = candidates.find(r => !r.prerelease && r.assets.some(a => a.name === 'ConeSRS-Windows.zip'))
      || candidates.find(r => r.assets.some(a => a.name === 'ConeSRS-Windows.zip'));
    if (!release) {
      status.textContent = 'The first Windows download is being prepared. Selected source is available on GitHub.';
      return;
    }
    const asset = release.assets.find(a => a.name === 'ConeSRS-Windows.zip');
    const url = new URL(asset.browser_download_url);
    if (url.origin !== 'https://github.com' || !url.pathname.startsWith('/kkaan/conesrs-releases/releases/download/')) throw new Error('Unexpected download URL');
    status.textContent = `${release.tag_name}${release.prerelease ? ' · Pre-release' : ''} · Windows 64-bit · ${(asset.size / 1048576).toFixed(0)} MB`;
    link.href = url.href;
    link.textContent = 'Download for Windows';
  } catch {
    status.textContent = 'Live release details are unavailable. Browse GitHub Releases for downloads and checksums.';
  }
})();
