UPDATE users SET application_settings = application_settings || '{
  "github_url": "https://github.com/HimJar911",
  "preferred_name": "Himanshu",
  "school": "Arizona State University",
  "degree": "Bachelors",
  "major": "Computer Science",
  "gpa": "3.52",
  "graduation_date": "May 2027",
  "location_state": "AZ",
  "location_country": "United States",
  "eeo_gender": "Male",
  "eeo_hispanic": false,
  "eeo_race": "Asian",
  "eeo_veteran": "I am not a protected veteran",
  "eeo_disability": "No, I do not have a disability and have not had one in the past",
  "work_authorized": true
}'::jsonb
WHERE id = '46e66cfa-e625-4ffc-b8dc-7bf75e21db26';
