UPDATE users SET application_settings = application_settings || '{
  "custom_answers": [
    {"questionKey": "where did you hear about", "questionText": "Where did you hear about this opportunity?", "answer": "LinkedIn"},
    {"questionKey": "how did you hear about this job opportunity", "questionText": "How did you hear about this job opportunity?", "answer": "LinkedIn"},
    {"questionKey": "why do you want to work here", "questionText": "Why do you want to work here?", "answer": "I build backend systems and I want to work somewhere where the infrastructure actually matters. The problems here are real and the scale is serious."},
    {"questionKey": "why are you interested in this role", "questionText": "Why are you interested in this role?", "answer": "I have shipped production systems end to end, from FastAPI backends to AWS deployments, and I want a role where that depth gets used, not just pattern matched on a resume."},
    {"questionKey": "tell us about yourself", "questionText": "Tell us about yourself", "answer": "CS junior at ASU, 3.52 GPA, graduating May 2027. I interned at Johnson and Johnson building a contract review system that cut manual work by 80%. I also built Persift, an autonomous job application pipeline that tracks 5000+ companies across 5 ATS platforms. I work best on hard backend problems with real constraints."},
    {"questionKey": "what are your strengths", "questionText": "What are your strengths?", "answer": "I pick up new systems fast and I ship. At J&J I went from onboarding to owning a production feature in two weeks. I am comfortable across the stack but my best work is backend, async pipelines, and infrastructure."},
    {"questionKey": "what is your greatest weakness", "questionText": "What is your greatest weakness?", "answer": "I move fast and sometimes skip documentation. I have gotten better at it. I now treat the README as part of the PR."},
    {"questionKey": "describe a challenge you faced", "questionText": "Describe a challenge you faced and how you overcame it", "answer": "At J&J, OCR output on scanned contracts was noisy and broke downstream rule engines. I built a validation layer that flagged low-confidence extractions and routed them to a secondary pipeline. Cut error rate by 80% without touching the core pipeline."},
    {"questionKey": "where do you see yourself in 5 years", "questionText": "Where do you see yourself in 5 years?", "answer": "Leading engineering on a product I helped build from early stage. I want to go deep on distributed systems and eventually own the technical direction of something."},
    {"questionKey": "what field are you looking to complete your internship", "questionText": "What field are you looking to complete your internship in?", "answer": "Software Engineering"},
    {"questionKey": "what term were you looking to start", "questionText": "What term were you looking to start your internship?", "answer": "September 2026"},
    {"questionKey": "how long of an internship are you looking for", "questionText": "How long of an internship are you looking for?", "answer": "12 months"},
    {"questionKey": "will you consent to a background check", "questionText": "Will you consent to a background check?", "answer": "Yes"},
    {"questionKey": "were you previously employed", "questionText": "Were you previously employed with this company?", "answer": "No"},
    {"questionKey": "are you available to work full time", "questionText": "Are you available to work full time?", "answer": "Yes"},
    {"questionKey": "are you able to commute", "questionText": "Are you able to commute to this location?", "answer": "Yes"},
    {"questionKey": "what is your expected date of graduation", "questionText": "What is your expected date of graduation?", "answer": "May 2027"},
    {"questionKey": "what is your expected graduation", "questionText": "What is your expected graduation date?", "answer": "May 2027"},
    {"questionKey": "do you have experience with", "questionText": "Do you have experience with our tech stack?", "answer": "Yes, I have worked with Python, JavaScript, TypeScript, REST APIs, Docker, AWS, and PostgreSQL in production environments."},
    {"questionKey": "are you currently enrolled", "questionText": "Are you currently enrolled in a degree program?", "answer": "Yes, B.S. Computer Science at Arizona State University, graduating May 2027."},
    {"questionKey": "veteran of the armed forces", "questionText": "If you are a veteran of the armed forces in your country", "answer": "I identify as a member of none of the listed veteran categories"},
    {"questionKey": "hourly compensation expectations", "questionText": "What are your hourly compensation expectations?", "answer": "25-35"},
    {"questionKey": "compensation expectations", "questionText": "What are your compensation expectations?", "answer": "25-35"},
    {"questionKey": "cover letter", "questionText": "Cover letter", "answer": "I build things that work in production. At Johnson and Johnson I shipped a contract review system that processed 50+ PDFs per day and cut manual review by 80%. Before that I built purchase order automation handling 10K+ monthly transactions with 100% uptime. Right now I am building Persift, an autonomous job application pipeline tracking 5000+ companies across 5 ATS platforms. I write clean backend code, I move fast, and I know how to ship. I would bring that same approach here."}
  ]
}'::jsonb
WHERE id = '46e66cfa-e625-4ffc-b8dc-7bf75e21db26';
