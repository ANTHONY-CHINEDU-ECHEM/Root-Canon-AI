"""UK dental guidance seed set.

A small, hand checked set of paraphrased summaries of real UK guidance, each
pointing at its authoritative public URL. It exists so that:

  * the service starts with a meaningful knowledge base before the full
    harvest has run (the full harvest indexes hundreds of thousands of records),
  * the interactive demo and the offline test suite run on real guidance rather
    than synthetic text.

Summaries are written in our own words to respect the publishers' copyright;
the full text is obtained by the live connectors under each source's licence.
Every figure below was checked against the linked source on the review date.
"""

from __future__ import annotations

from datetime import date

from backend.app.domain import Licence, SourceDocument, SourceType

REVIEWED = date(2026, 10, 27)
NOTE = {"seed_note": "Paraphrased summary of the linked source, used for offline bootstrap and the demo."}


def _doc(doc_id, title, url, publisher, sections, year, source_type=SourceType.UK_GUIDELINE,
         licence=Licence.UNKNOWN, source="seed") -> SourceDocument:  # type: ignore[no-untyped-def]
    return SourceDocument(
        doc_id=f"seed:{doc_id}", source=source, source_type=source_type, title=title, url=url,
        publisher=publisher, published=date(year, 1, 1), updated=REVIEWED, licence=licence,
        jurisdiction="UK", sections=sections, text="\n\n".join(f"{h}: {b}" for h, b in sections), extra=NOTE,
    )


SEED_DOCUMENTS: list[SourceDocument] = [
    _doc("sdcep-amoxicillin", "SDCEP Drug Prescribing for Dentistry: Amoxicillin for dental abscess",
         "https://sdcepdentalprescribing.nhs.scot/guidance/bacterial-infections/dental-abscess/first-line-antibiotics/amoxicillin",
         "Scottish Dental Clinical Effectiveness Programme", [
             ("ROLE", "Amoxicillin is an effective first line antibiotic for a dental abscess and is absorbed better "
                      "than phenoxymethylpenicillin. Patients who have completed a course of antibiotic treatment "
                      "should be reviewed."),
             ("ADULT REGIMEN", "For adults the suggested 5 day regimen is amoxicillin 500 mg capsules, one capsule "
                               "three times daily, supplying 15 capsules."),
             ("PAEDIATRIC REGIMEN", "For children the dose is set by age: 6 to 11 months 125 mg three times daily; "
                                    "1 to 4 years 250 mg three times daily; 5 to 11 years 500 mg three times "
                                    "daily; 12 to 17 years 500 mg three times daily. Capsules of 250 mg or oral "
                                    "suspension of 125 mg/5 ml or 250 mg/5 ml may be used."),
         ], 2021),
    _doc("sdcep-2021-update", "SDCEP Drug Prescribing for Dentistry: 2021 update on antibiotic choice",
         "https://sdcep.org.uk/news/update-to-drug-prescribing-guidance-now-available/",
         "Scottish Dental Clinical Effectiveness Programme", [
             ("FIRST CHOICE ANTIBIOTIC", "The 2021 update to the third edition, aligned with BNF 81, makes "
                                         "phenoxymethylpenicillin the preferred first choice antibiotic for "
                                         "dento alveolar infections because its narrower spectrum is less likely "
                                         "to drive antimicrobial resistance. The suggested adult regimen is "
                                         "phenoxymethylpenicillin 500 mg four times daily for 5 days."),
             ("WHEN TO PRESCRIBE", "The situations in which an antibiotic is appropriate are unchanged. Local "
                                   "measures such as drainage, extraction or pulp extirpation should be used "
                                   "first, and antibiotics are reserved for spreading infection or systemic "
                                   "involvement such as fever or lymphadenopathy."),
         ], 2021),
    _doc("sdcep-metronidazole", "SDCEP Drug Prescribing for Dentistry: Metronidazole for acute periodontal conditions",
         "https://sdcepdentalprescribing.nhs.scot/guidance/bacterial-infections/acute-periodontal-conditions/metronidazole/",
         "Scottish Dental Clinical Effectiveness Programme", [
             ("INDICATION", "Metronidazole is used for necrotising periodontal conditions when there is systemic "
                            "involvement or local measures alone are insufficient, alongside debridement and oral "
                            "hygiene instruction. It is also an option for dental abscess in penicillin allergy."),
             ("ADULT REGIMEN", "The adult regimen is metronidazole 400 mg three times daily for 3 days for "
                               "necrotising periodontal disease. The 2021 update set the adult dental abscess "
                               "regimen at 400 mg three times daily for 5 days."),
             ("CAUTIONS", "Patients must avoid alcohol during the course and for 48 hours afterwards because of a "
                          "disulfiram like reaction. Metronidazole enhances the anticoagulant effect of warfarin."),
         ], 2021),
    _doc("sdcep-ibuprofen", "SDCEP Drug Prescribing for Dentistry: Ibuprofen for odontogenic pain",
         "https://sdcepdentalprescribing.nhs.scot/guidance/odontogenic-pain/analgesics/ibuprofen/",
         "Scottish Dental Clinical Effectiveness Programme", [
             ("REGIMEN", "For adults with dental pain the suggested regimen is ibuprofen 400 mg four times daily, "
                         "preferably after food, for up to 5 days."),
             ("CAUTIONS", "Non steroidal anti inflammatory drugs should be avoided or used with caution in patients "
                          "with asthma worsened by NSAIDs, a history of peptic ulceration, renal impairment, heart "
                          "failure, late pregnancy, and in those taking anticoagulants, where paracetamol is preferred."),
         ], 2021),
    _doc("sdcep-paracetamol", "SDCEP Drug Prescribing for Dentistry: Paracetamol for odontogenic pain",
         "https://sdcepdentalprescribing.nhs.scot/guidance/odontogenic-pain/analgesics/paracetamol/",
         "Scottish Dental Clinical Effectiveness Programme", [
             ("REGIMEN", "For adults the suggested regimen is paracetamol 1 g four times daily for up to 5 days, "
                         "with a maximum of 4 g in 24 hours."),
             ("CAUTIONS", "A lower dose is needed for adults weighing under 50 kg and for patients with hepatic "
                          "impairment or chronic alcohol dependence. Paracetamol is the analgesic of choice for "
                          "patients taking anticoagulants."),
         ], 2021),
    _doc("nice-cg64", "NICE CG64: Prophylaxis against infective endocarditis",
         "https://www.nice.org.uk/guidance/cg64", "National Institute for Health and Care Excellence", [
             ("RECOMMENDATION", "Antibiotic prophylaxis against infective endocarditis is not recommended routinely "
                                "for people undergoing dental procedures. Chlorhexidine mouthwash should not be "
                                "offered as prophylaxis against infective endocarditis."),
             ("2016 AMENDMENT", "In 2016 NICE added the word routinely to the recommendation, acknowledging that in "
                                "individual cases prophylaxis may be appropriate after discussion with the patient "
                                "and their cardiology team."),
             ("INFECTION MANAGEMENT", "Any episode of infection in people at risk of infective endocarditis should "
                                      "be investigated and treated promptly to reduce the risk of endocarditis."),
         ], 2016, licence=Licence.SYNDICATION_LICENSED),
    _doc("sdcep-ie", "SDCEP: Antibiotic prophylaxis against infective endocarditis implementation advice",
         "https://sdcepdentalprescribing.nhs.scot/guidance/bacterial-infections/infective-endocarditis/",
         "Scottish Dental Clinical Effectiveness Programme", [
             ("SPECIAL RISK PATIENTS", "Patients at increased risk include those with a prosthetic valve or prior "
                                       "valve repair with prosthetic material, previous infective endocarditis, and "
                                       "some congenital heart disease. For these patients the need for prophylaxis "
                                       "before invasive procedures should be discussed with the cardiologist and the "
                                       "patient, and the decision recorded."),
             ("REGIMEN WHEN INDICATED", "If prophylaxis is agreed for an adult, the regimen is amoxicillin 3 g orally "
                                        "60 minutes before the procedure, or clindamycin 600 mg orally 60 minutes "
                                        "before the procedure for patients allergic to penicillin."),
         ], 2018),
    _doc("nice-cg19", "NICE CG19: Dental checks, intervals between oral health reviews",
         "https://www.nice.org.uk/guidance/cg19", "National Institute for Health and Care Excellence", [
             ("RECALL INTERVAL", "The interval between oral health reviews should be set for each patient after a "
                                 "risk assessment at every review. For adults it should range from a minimum of 3 "
                                 "months to a maximum of 24 months. For patients younger than 18 years it should "
                                 "range from 3 months to 12 months."),
             ("RISK FACTORS", "The interval is informed by medical history, social history, dietary habits, fluoride "
                              "exposure, clinical findings such as caries and periodontal status, and the patient's "
                              "ability to maintain oral health."),
         ], 2004, licence=Licence.SYNDICATION_LICENSED),
    _doc("dboh-fluoride", "Delivering better oral health: Chapter 9 fluoride",
         "https://www.gov.uk/government/publications/delivering-better-oral-health-an-evidence-based-toolkit-for-prevention/chapter-9-fluoride",
         "Office for Health Improvement and Disparities", [
             ("TOOTHPASTE BY AGE", "Children under 3 years should use a smear of toothpaste containing no less than "
                                   "1,000 ppm fluoride. Children aged 3 to 6 years should use a pea sized amount "
                                   "containing more than 1,000 ppm fluoride. Children from 7 years and adults should "
                                   "use toothpaste containing 1,350 to 1,500 ppm fluoride, which is also advised for "
                                   "younger children at higher risk of caries."),
             ("SPIT DO NOT RINSE", "Patients should spit out excess toothpaste after brushing and avoid rinsing, so "
                                   "fluoride stays on the teeth."),
             ("HIGHER CONCENTRATION", "The highest fluoride concentration sold over the counter in the UK is 1,500 "
                                      "ppm. Sodium fluoride 2,800 ppm toothpaste can be prescribed for patients aged 10 "
                                      "years and over, and 5,000 ppm toothpaste for patients aged 16 years and over, "
                                      "when caries risk is high. Risk should be reviewed at routine assessments."),
             ("FLUORIDE VARNISH", "Fluoride varnish at 22,600 ppm should be applied twice yearly for all children "
                                  "from 3 years, and two or more times a year for children and adults at higher "
                                  "risk of caries."),
         ], 2021, licence=Licence.OPEN_GOVERNMENT),
    _doc("sdcep-emergency-drugs", "SDCEP Practice Support Manual: Medical emergency drugs",
         "https://www.psm.sdcep.org.uk/topics/medical-emergencies-and-life-support/medical-emergency-drugs/",
         "Scottish Dental Clinical Effectiveness Programme", [
             ("REQUIRED DRUGS", "Every dental practice must have immediate access to adrenaline 1 ml ampoules or "
                                "prefilled syringes of 1:1000 solution for intramuscular injection, glyceryl "
                                "trinitrate spray 400 micrograms per metered dose, salbutamol inhaler 100 micrograms "
                                "per actuation, dispersible aspirin 300 mg, glucagon 1 mg for intramuscular "
                                "injection, oral glucose, buccal midazolam, and medical oxygen."),
             ("WHO MAY ADMINISTER", "The Prescription Only Medicines (Human Use) Order 1997 allows anyone to "
                                    "administer adrenaline and glucagon for the purpose of saving life in an "
                                    "emergency, so all trained dental team members may give them. Midazolam is a "
                                    "Schedule 3 controlled drug and its storage must comply with that legislation."),
         ], 2021),
    _doc("rcuk-anaphylaxis", "Resuscitation Council UK: Emergency treatment of anaphylaxis in dental practice",
         "https://www.resus.org.uk/library/additional-guidance/guidance-anaphylaxis/emergency-treatment",
         "Resuscitation Council UK", [
             ("ADRENALINE DOSE", "Give intramuscular adrenaline 1:1000 into the anterolateral thigh: 500 micrograms "
                                 "(0.5 mL) for adults and children over 12 years, 300 micrograms (0.3 mL) for children "
                                 "aged 6 to 12 years, and 150 micrograms (0.15 mL) for children under 6 years."),
             ("REPEAT AND SUPPORT", "Repeat the dose after 5 minutes if there is no improvement. Call 999, follow the "
                                    "ABCDE approach, lie the patient flat with legs raised unless breathing is "
                                    "difficult, and give high flow oxygen."),
         ], 2021),
    _doc("scotgov-emergencies", "Scottish Government: Emergency drugs and equipment in primary dental care",
         "https://www.gov.scot/publications/emergency-drugs-equipment-primary-dental-care/pages/3/",
         "Scottish Government", [
             ("EMERGENCIES TO PREPARE FOR", "The BNF section on prescribing in dental practice lists the medical "
                                            "emergencies a dental team must be ready to manage: adrenal insufficiency, "
                                            "anaphylaxis, asthma, cardiac emergencies, epileptic seizures, "
                                            "hypoglycaemia and syncope. Aspiration, choking and stroke may also occur."),
             ("APPROACH", "Every medical emergency should be assessed and treated with the Airway, Breathing, "
                          "Circulation, Disability, Exposure (ABCDE) approach."),
         ], 2022, licence=Licence.OPEN_GOVERNMENT),
    _doc("sdcep-anticoagulants", "SDCEP: Management of dental patients taking anticoagulants or antiplatelet drugs",
         "https://www.sdcep.org.uk/published-guidance/anticoagulants-and-antiplatelets/",
         "Scottish Dental Clinical Effectiveness Programme", [
             ("WARFARIN", "For patients taking warfarin, check the INR ideally within 24 hours before treatment, or "
                          "up to 72 hours before for patients with a stable INR. If the INR is below 4, treat "
                          "without interrupting warfarin, using local haemostatic measures."),
             ("DIRECT ORAL ANTICOAGULANTS", "For procedures with a low bleeding risk, treat without interrupting the "
                                            "drug. For procedures more likely to cause bleeding, patients taking "
                                            "apixaban or dabigatran twice daily should miss the morning dose, and "
                                            "patients taking rivaroxaban or edoxaban once daily in the morning "
                                            "should delay the dose until 4 hours after haemostasis."),
             ("ANTIPLATELETS", "Antiplatelet drugs should not be interrupted before dental treatment. Expect "
                               "prolonged bleeding and use local measures such as packing and suturing."),
         ], 2015),
    _doc("sdcep-mronj", "SDCEP: Oral health management of patients at risk of medication related osteonecrosis of the jaw",
         "https://www.sdcep.org.uk/published-guidance/medication-related-osteonecrosis-of-the-jaw/",
         "Scottish Dental Clinical Effectiveness Programme", [
             ("RISK GROUPS", "Patients taking antiresorptive drugs such as bisphosphonates or denosumab for "
                             "osteoporosis are generally at low risk of MRONJ. Patients treated with these drugs for "
                             "cancer, or taking them with systemic glucocorticoids or for more than 5 years, are at "
                             "higher risk."),
             ("MANAGEMENT", "Ideally make the patient dentally fit before antiresorptive therapy starts. Extractions "
                            "for low risk patients can usually be performed in primary care. Do not advise patients "
                            "to stop their antiresorptive drug; there is no evidence that a drug holiday reduces risk."),
         ], 2017),
    _doc("nice-ng12-head-neck", "NICE NG12: Suspected cancer recognition and referral, head and neck",
         "https://www.nice.org.uk/guidance/ng12", "National Institute for Health and Care Excellence", [
             ("DENTAL REFERRAL", "A dentist should consider an urgent referral, for an appointment within 2 weeks, "
                                 "for a lump on the lip or in the oral cavity, or a red or red and white patch in "
                                 "the oral cavity consistent with erythroplakia or erythroleukoplakia."),
             ("GENERAL PRACTICE REFERRAL", "Refer through a suspected cancer pathway for unexplained ulceration of "
                                           "the oral cavity lasting more than 3 weeks or a persistent and "
                                           "unexplained lump in the neck."),
         ], 2015, licence=Licence.SYNDICATION_LICENSED),
    _doc("bhvs-ie-review", "A change in the NICE guidelines on antibiotic prophylaxis: British Heart Valve Society update",
         "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6172668/", "British Heart Valve Society", [
             ("SUMMARY", "The British Heart Valve Society reviewed the 2016 change to NICE CG64. It explains that adding "
                         "the word routinely allows clinicians to consider prophylaxis for selected high risk "
                         "patients, and recommends that cardiologists and dentists agree a plan for those patients."),
         ], 2018, source_type=SourceType.NARRATIVE_REVIEW, licence=Licence.CC_BY),
]


def seed_documents() -> list[SourceDocument]:
    return list(SEED_DOCUMENTS)
