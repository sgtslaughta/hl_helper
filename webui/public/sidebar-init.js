(function () {
	try {
		var raw = localStorage.getItem('sidebar-store');
		var parsed = raw ? JSON.parse(raw) : null;
		var collapsed = !!(parsed && parsed.state && parsed.state.collapsed);
		document.documentElement.style.setProperty(
			'--sidebar-w',
			collapsed ? '3.5rem' : '15rem',
		);
		document.documentElement.dataset.sidebarCollapsed = collapsed ? '1' : '0';
	} catch (e) {
		document.documentElement.style.setProperty('--sidebar-w', '15rem');
		document.documentElement.dataset.sidebarCollapsed = '0';
	}
})();
