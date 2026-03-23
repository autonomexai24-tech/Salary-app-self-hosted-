export interface Employee {
  id: string;
  name: string;
  department: string;
  designation: string;
  dailyRate: number;
  monthlyBasic: number;
  avatar: string; // initials
}

export interface AttendanceEntry {
  employeeId: string;
  timeIn: string;  // "HH:mm" or ""
  timeOut: string; // "HH:mm" or ""
  advance: number;
}

export const MOCK_EMPLOYEES: Employee[] = [
  { id: "e1", name: "Rajesh Kumar", department: "Printing", designation: "Operator", dailyRate: 800, monthlyBasic: 20800, avatar: "RK" },
  { id: "e2", name: "Priya Sharma", department: "Binding", designation: "Senior Binder", dailyRate: 750, monthlyBasic: 19500, avatar: "PS" },
  { id: "e3", name: "Amit Patel", department: "Design", designation: "Graphic Designer", dailyRate: 1200, monthlyBasic: 31200, avatar: "AP" },
  { id: "e4", name: "Sunita Devi", department: "Cutting", designation: "Operator", dailyRate: 700, monthlyBasic: 18200, avatar: "SD" },
  { id: "e5", name: "Vikram Singh", department: "Printing", designation: "Lead Operator", dailyRate: 1000, monthlyBasic: 26000, avatar: "VS" },
  { id: "e6", name: "Meera Joshi", department: "Admin", designation: "Office Coordinator", dailyRate: 900, monthlyBasic: 23400, avatar: "MJ" },
  { id: "e7", name: "Arjun Reddy", department: "Binding", designation: "Helper", dailyRate: 550, monthlyBasic: 14300, avatar: "AR" },
  { id: "e8", name: "Kavita Nair", department: "Design", designation: "Junior Designer", dailyRate: 850, monthlyBasic: 22100, avatar: "KN" },
];

export const SEED_ATTENDANCE: AttendanceEntry[] = [
  { employeeId: "e1", timeIn: "09:00", timeOut: "18:00", advance: 0 },
  { employeeId: "e2", timeIn: "09:22", timeOut: "18:00", advance: 500 },
  { employeeId: "e3", timeIn: "08:55", timeOut: "19:30", advance: 0 },
  { employeeId: "e5", timeIn: "09:05", timeOut: "18:00", advance: 0 },
  { employeeId: "e6", timeIn: "09:45", timeOut: "18:00", advance: 8000 },
];
