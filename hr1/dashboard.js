function loadPage(pageId) {
  const content = document.getElementById('page-content');

  switch(pageId) {
    case 'overview':
      content.innerHTML = `<h1 class="page-title">Admin Dashboard</h1><p>Welcome, Admin!</p>`;
      break;
    case 'employee-management':
      content.innerHTML = `<h1 class="page-title">Employee Management</h1>`;
      break;
    case 'department-management':
      content.innerHTML = `<h1 class="page-title">Department Management</h1>`;
      break;
    case 'attendance-leave':
      content.innerHTML = `<h1 class="page-title">Attendance & Leave</h1>`;
      break;
    case 'payroll-management':
      content.innerHTML = `<h1 class="page-title">Payroll Management</h1>`;
      break;
    case 'reports-analytics':
      content.innerHTML = `<h1 class="page-title">Reports & Analytics</h1>`;
      break;
    case 'settings':
      content.innerHTML = `<h1 class="page-title">Settings</h1>`;
      break;

    case 'team-overview':
      content.innerHTML = `<h1 class="page-title">Team Overview</h1>`;
      break;
    case 'leave-attendance':
      content.innerHTML = `<h1 class="page-title">Leave & Attendance</h1>`;
      break;
    case 'performance':
      content.innerHTML = `<h1 class="page-title">Performance</h1>`;
      break;
    case 'reports':
      content.innerHTML = `<h1 class="page-title">Reports</h1>`;
      break;

    case 'personal-overview':
      content.innerHTML = `<h1 class="page-title">Personal Overview</h1>`;
      break;
    case 'leave-management':
      content.innerHTML = `<h1 class="page-title">Leave Management</h1>`;
      break;
    case 'attendance-tracking':
      content.innerHTML = `<h1 class="page-title">Attendance Tracking</h1>`;
      break;
    case 'payroll':
      content.innerHTML = `<h1 class="page-title">Payroll</h1>`;
      break;

    case 'recruitment':
      content.innerHTML = `<h1 class="page-title">Recruitment Tracking</h1>`;
      break;
    case 'onboarding':
      content.innerHTML = `<h1 class="page-title">Onboarding/Offboarding</h1>`;
      break;
    case 'compliance':
      content.innerHTML = `<h1 class="page-title">Compliance & Policy</h1>`;
      break;
    case 'training':
      content.innerHTML = `<h1 class="page-title">Training & Development</h1>`;
      break;

    default:
      content.innerHTML = `<h1 class="page-title">Dashboard</h1>`;
  }
}
