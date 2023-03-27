import logging

from flask_wtf import FlaskForm
from wtforms import (
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    TimeField,
    RadioField
)
from wtforms.validators import (
    URL,
    DataRequired,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Regexp,
    ValidationError
)

from registry.util import (
    get_fresh_desk_api,
    get_admin_harbor_api,
    get_harbor_user,
    get_harbor_projects,
    is_soteria_researcher
)

requirement_choices = [
    ("", "Select Requirement Met"),
    ("a-xrac", "Active XRAC allocation."),
    ("b-listed-and-published", "Institute Member and Recently Published"),
    ("c-active-grant-on-ORCID", "Active Federal Grant on ORCID Profile"),
    ("d-institution-non-R1-HBCU-TCU", "Non R1, HBCU, or TCU institute member"),
    ("e-pi-approval", "SOTERIA PI approval"),
]

MAX_PRIVATE_PROJECTS = 2
MAX_PUBLIC_PROJECTS = 3


def validate_visibility(form, field):
    def project_is_public(project: dict):
        return project.get('metadata', 'false').get('public', 'false') == 'true'

    users_projects = get_harbor_projects()

    public_projects = list(filter(project_is_public, users_projects))
    private_projects = list(filter(lambda x: not project_is_public(x), users_projects))

    if field.data == 'private' and len(private_projects) >= MAX_PRIVATE_PROJECTS:
        raise ValidationError(
            f"You have been allocated the maximum amount of private projects, contact support if you need more."
        )

    elif field.data == 'public' and len(public_projects) >= MAX_PUBLIC_PROJECTS:
        raise ValidationError(
            f"You have been allocated the maximum amount of public projects, contact support if you need more."
        )

    return True


class CreateProjectForm(FlaskForm):
    project_name = StringField("Name", validators=[InputRequired()])
    visibility = RadioField(
        "Visibility",
        choices=[("public", "Public"), ("private", "Private")],
        validators=[validate_visibility]
    )
    submit = SubmitField("Submit")

    def validate(self, *args, **kwargs):
        if not is_soteria_researcher():
            return False

        self.project_name.validate(self)
        self.visibility.validate(self)

        if self.errors:
            return False

        return True

    def submit_request(self):

        harbor_user = get_harbor_user()
        harbor_api = get_admin_harbor_api()

        response = harbor_api.create_project(self.project_name.data, self.visibility.data == "public")
        harbor_api.add_project_member(response['project_id'], harbor_user['username'], role_id=4)

        return response


class ResearcherApprovalForm(FlaskForm):
    email = StringField("Institute Affiliated Email", validators=[InputRequired()])
    criteria = SelectField(
        "Requirement Met", choices=requirement_choices, validators=[InputRequired()]
    )

    b_website_url = StringField("Website URL", validators=[URL(), InputRequired()])
    b_publication_doi = StringField("Publication DOI", validators=[InputRequired()])

    c_grant_number = StringField("Grant Number", validators=[InputRequired()])
    c_funding_agency = StringField("Funding Agency", validators=[InputRequired()])

    d_website_url = StringField("Website URL", validators=[URL(), InputRequired()])
    d_classification = StringField("Institution Classification", validators=[InputRequired()])

    submit = SubmitField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.a_fields = []
        self.b_fields = [self.b_website_url, self.b_publication_doi]
        self.c_fields = [self.c_grant_number, self.c_funding_agency]
        self.d_fields = [self.d_website_url, self.d_classification]
        self.e_fields = []

    class Meta:
        csrf = False  # CSRF not needed because no data gets modified

    def validate(self):

        self.email.validate(self)

        if not self.criteria.validate(self):
            return False

        # Validate that the requirements are met for the selected criteria
        criteria_fields = self.get_criteria_fields()
        return all(field.validate(self) for field in criteria_fields)

    def get_criteria_fields(self):
        if self.criteria.data == "b-listed-and-published":
            return self.b_fields

        if self.criteria.data == "c-active-grant-on-ORCID":
            return self.c_fields

        if self.criteria.data == "d-institution-non-R1-HBCU-TCU":
            return self.d_fields

        return []

    def submit_request(self):
        api = get_fresh_desk_api()
        selected_requirement = next(
            x[1] for x in requirement_choices if x[0] == self.criteria.data
        )
        description = f"""
            <div>
              <p>
                Researcher has selected that they meet requirement: {selected_requirement}
              </p>
            """
        for field in self.get_criteria_fields():
            description += f"""
                <h5>
                    {field.label.text}
                </h5>
                <p>
                    {field.data}
                </p>
            """
        description += "</div>"

        ticket = {
            "name": "TODO LAST",
            "email": self.email.data,
            "subject": "SOTERIA Researcher Application",
            "description": description,
            "group_id": 12000006916,
            "priority": 2,
            "status": 2,
            "type": "SOTERIA Researcher Application",
        }

        response = api.create_ticket(**ticket)

        if response.status_code == 201:
            return True
        else:
            return False
